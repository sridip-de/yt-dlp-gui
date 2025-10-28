#!/usr/bin/env python3
import gi
import os
import threading
import subprocess
import json
import sys
import shutil
import traceback
from pathlib import Path
from collections import deque
from urllib.parse import urlparse

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

# -----------------------
# Helper logging functions
# -----------------------
def _safe_idle(fn, *args):
    """Call GLib.idle_add safely for UI updates"""
    try:
        return GLib.idle_add(fn, *args)
    except Exception:
        # worst-case: nothing we can do
        return None


class YtDlpGUI(Gtk.ApplicationWindow):
    FORMAT_OPTIONS = {
        "audio": [("best", "Best (auto)"), ("mp3", "MP3"), ("m4a", "M4A"), ("wav", "WAV"), ("opus", "Opus")]
    }

    SUB_LANGS = [("en", "English"), ("all", "All Available"), ("es", "Spanish"),
                 ("fr", "French"), ("de", "German"), ("hi", "Hindi")]

    # how many recent lines from yt-dlp to keep for debugging
    RECENT_LINES = 400

    def __init__(self, app):
        super().__init__(application=app, title="yt-dlp GUI Manager")
        self.set_default_size(800, 900)
        self.set_border_width(10)
        self.set_icon_name("application-x-executable")

        self.download_thread = None
        self.process = None
        self.available_formats = {}
        self._recent_output = deque(maxlen=self.RECENT_LINES)

        self.setup_ui()

    # ---------- logging helpers (all logs go to status view) ----------
    def log(self, level, category, message, debug=None):
        """
        Generic logger for the status box.
        level: INFO / WARN / ERROR / DEBUG
        category: short tag like Network / yt-dlp / Parsing / Process
        message: user-facing message
        debug: optional dict or string with further diagnostic info
        """
        prefix = f"[{level}][{category}] "
        lines = [prefix + message]
        if debug:
            if isinstance(debug, dict):
                for k, v in debug.items():
                    lines.append(f"[{level}][{category}][DEBUG]{k}: {v}")
            else:
                lines.append(f"[{level}][{category}][DEBUG] {str(debug)}")

        # Add to recent output buffer for process debugging
        for l in lines:
            self._recent_output.append(l)

        # Add to GUI in main thread
        _safe_idle(self._append_status_lines, "\n".join(lines))

    def log_info(self, category, message, debug=None):
        self.log("INFO", category, message, debug)

    def log_warn(self, category, message, debug=None):
        self.log("WARN", category, message, debug)

    def log_error(self, category, message, debug=None):
        self.log("ERROR", category, message, debug)

    def log_debug(self, category, message, debug=None):
        # Put debug at DEBUG level; GUI still shows it but may be filtered by user mentally
        self.log("DEBUG", category, message, debug)

    def _append_status_lines(self, text):
        """Append text to the status TextView (runs on main thread)."""
        try:
            text_buffer = self.status_view.get_buffer()
            text_buffer.insert(text_buffer.get_end_iter(), text + "\n")
            # scroll to end
            insert_mark = text_buffer.get_insert()
            try:
                self.status_view.scroll_to_mark(insert_mark, 0.0, True, 0.0, 1.0)
            except Exception:
                end_iter = text_buffer.get_end_iter()
                self.status_view.scroll_to_iter(end_iter, 0.0, True, 0.0, 1.0)
        except Exception:
            # if logging itself fails, fallback to printing to stderr
            print("Failed to append status lines:", text, file=sys.stderr)

    # ---------- UI creation ----------
    def create_labeled_combo(self, label_text, options, active_id="best"):
        """Helper to create labeled comboboxes"""
        label = Gtk.Label(label=label_text, xalign=0)
        combo = Gtk.ComboBoxText()
        for opt_id, opt_label in options:
            combo.append(opt_id, opt_label)
        try:
            combo.set_active_id(active_id)
        except Exception:
            pass
        return label, combo

    def create_frame(self, title, spacing=8):
        """Helper to create styled frames"""
        frame = Gtk.Frame(label=title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        for margin in ["top", "bottom", "start", "end"]:
            getattr(box, f"set_margin_{margin}")(10)
        frame.add(box)
        return frame, box

    def setup_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_box)

        # URL Input
        url_label = Gtk.Label(label="URL:", xalign=0)
        url_box = Gtk.Box(spacing=5)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text("Enter YouTube URL...")
        self.fetch_btn = Gtk.Button(label="Fetch Formats")
        self.fetch_btn.connect("clicked", self.on_fetch_formats)
        url_box.pack_start(self.url_entry, True, True, 0)
        url_box.pack_start(self.fetch_btn, False, False, 0)
        main_box.pack_start(url_label, False, False, 0)
        main_box.pack_start(url_box, False, False, 0)

        # Download Type Selection
        type_label = Gtk.Label(label="Download Type:", xalign=0)
        type_box = Gtk.Box(spacing=10)
        self.type_combo = Gtk.ComboBoxText()
        self.type_combo.append("video", "Video")
        self.type_combo.append("audio", "Audio Only")
        self.type_combo.set_active_id("video")
        self.type_combo.connect("changed", self.on_type_changed)
        type_box.pack_start(self.type_combo, False, False, 0)

        self.playlist_check = Gtk.CheckButton(label="Download Playlist")
        type_box.pack_start(self.playlist_check, False, False, 0)

        main_box.pack_start(type_label, False, False, 0)
        main_box.pack_start(type_box, False, False, 0)

        # Video Settings Frame
        self.video_frame, video_box = self.create_frame("Video Settings")

        v_format_label = Gtk.Label(label="Available Format:", xalign=0)
        self.v_format_combo = Gtk.ComboBoxText()
        self.v_format_combo.append("best", "Loading... (fetch URL first)")
        try:
            self.v_format_combo.set_active_id("best")
        except Exception:
            pass
        video_box.pack_start(v_format_label, False, False, 0)
        video_box.pack_start(self.v_format_combo, False, False, 0)

        # Format info display
        self.format_info_label = Gtk.Label(label="Select a format to see details", xalign=0)
        self.format_info_label.set_line_wrap(True)
        video_box.pack_start(self.format_info_label, False, False, 0)

        self.v_format_combo.connect("changed", self.on_video_format_changed)

        main_box.pack_start(self.video_frame, False, False, 0)

        # Audio Settings Frame
        audio_frame, audio_box = self.create_frame("Audio Settings")

        a_format_label, self.a_format_combo = self.create_labeled_combo(
            "Audio Format:", self.FORMAT_OPTIONS["audio"], "best"
        )
        audio_box.pack_start(a_format_label, False, False, 0)
        audio_box.pack_start(self.a_format_combo, False, False, 0)

        self.thumbnail_check = Gtk.CheckButton(label="Embed Thumbnail in Audio")
        audio_box.pack_start(self.thumbnail_check, False, False, 0)

        main_box.pack_start(audio_frame, False, False, 0)

        # Subtitle Settings Frame
        sub_frame, sub_box = self.create_frame("Subtitle Settings")

        self.subtitle_check = Gtk.CheckButton(label="Download Subtitles")
        self.subtitle_check.connect("toggled", self.on_subtitle_toggled)
        sub_box.pack_start(self.subtitle_check, False, False, 0)

        self.embed_sub_check = Gtk.CheckButton(label="Embed Subtitles in Video")
        self.embed_sub_check.set_sensitive(False)
        sub_box.pack_start(self.embed_sub_check, False, False, 0)

        sub_lang_label, self.sub_lang_combo = self.create_labeled_combo(
            "Subtitle Language:", self.SUB_LANGS, "en"
        )
        self.sub_lang_combo.set_sensitive(False)
        sub_box.pack_start(sub_lang_label, False, False, 0)
        sub_box.pack_start(self.sub_lang_combo, False, False, 0)

        main_box.pack_start(sub_frame, False, False, 0)

        # Download Location
        loc_label = Gtk.Label(label="Download Location:", xalign=0)
        loc_box = Gtk.Box(spacing=5)
        self.location_entry = Gtk.Entry()
        self.location_entry.set_text(str(Path.home() / "Downloads"))
        browse_btn = Gtk.Button(label="Browse")
        browse_btn.connect("clicked", self.on_browse_clicked)
        loc_box.pack_start(self.location_entry, True, True, 0)
        loc_box.pack_start(browse_btn, False, False, 0)

        main_box.pack_start(loc_label, False, False, 0)
        main_box.pack_start(loc_box, False, False, 0)

        # Progress Section
        progress_label = Gtk.Label(label="Progress:", xalign=0)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)

        scroll_win = Gtk.ScrolledWindow()
        scroll_win.set_size_request(-1, 150)
        self.status_view = Gtk.TextView()
        self.status_view.set_editable(False)
        scroll_win.add(self.status_view)

        main_box.pack_start(progress_label, False, False, 0)
        main_box.pack_start(self.progress_bar, False, False, 0)
        main_box.pack_start(scroll_win, True, True, 0)

        # Buttons
        button_box = Gtk.Box(spacing=5)
        download_btn = Gtk.Button(label="Download")
        download_btn.connect("clicked", self.on_download_clicked)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_cancel_clicked)
        clear_btn = Gtk.Button(label="Clear Log")
        clear_btn.connect("clicked", self.on_clear_log)

        button_box.pack_start(download_btn, True, True, 0)
        button_box.pack_start(cancel_btn, True, True, 0)
        button_box.pack_start(clear_btn, True, True, 0)

        main_box.pack_end(button_box, False, False, 0)

        self.show_all()
        self.video_frame.hide()

    # ---------- UI callbacks ----------
    def on_type_changed(self, combo):
        is_video = combo.get_active_id() == "video"
        self.video_frame.set_visible(is_video)
        self.embed_sub_check.set_sensitive(is_video and self.subtitle_check.get_active())

    def on_subtitle_toggled(self, check):
        is_active = check.get_active()
        self.sub_lang_combo.set_sensitive(is_active)
        self.embed_sub_check.set_sensitive(is_active and self.type_combo.get_active_id() == "video")

    def on_video_format_changed(self, combo):
        """Update format info when selection changes"""
        format_id = combo.get_active_id()
        if format_id in self.available_formats:
            info = self.available_formats[format_id]
            self.format_info_label.set_text(info)

    def on_fetch_formats(self, button):
        """Fetch available formats from URL"""
        url = self.url_entry.get_text().strip()
        if not url:
            self.log_error("Input", "Please enter a URL")
            return

        # Validate URL minimally
        if not self._looks_like_url(url):
            self.log_error("Input", "URL does not look valid", {"url": url})
            return

        # Check yt-dlp presence
        if not shutil.which("yt-dlp"):
            self.log_error("yt-dlp", "yt-dlp not found on PATH. Install via: pip install yt-dlp",
                           {"hint": "or add the path to yt-dlp binary to your PATH"})
            return

        self.fetch_btn.set_sensitive(False)
        self.fetch_btn.set_label("Fetching...")

        fetch_thread = threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True)
        fetch_thread.start()

    def fetch_formats_thread(self, url):
        """Thread to fetch available formats"""
        try:
            cmd = ["yt-dlp", "--list-formats", "-R", "5", url]
            self.log_info("yt-dlp", "Running format-list command", {"cmd": " ".join(cmd)})
            try:
                # run with timeout and capture both stdout/stderr
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired as te:
                # Provide debug info
                debug = {
                    "cmd": " ".join(cmd),
                    "timeout": 30,
                    "exception": str(te)
                }
                self.log_error("Network", "Timeout fetching formats", debug)
                return

            stdout = result.stdout or ""
            stderr = result.stderr or ""
            rc = result.returncode
            debug_info = {"returncode": rc, "cmd": " ".join(cmd)}
            if stderr.strip():
                debug_info["stderr_tail"] = stderr.strip()[-1000:]  # last part for brevity
                self.log_debug("yt-dlp", "stderr present while listing formats", {"stderr": stderr.strip()[:1000]})

            if rc != 0:
                # non-zero exit: log error with stdout/stderr context
                debug_info["stdout_tail"] = stdout.strip()[-1000:]
                self.log_error("yt-dlp", f"yt-dlp exited with code {rc} while listing formats", debug_info)
                # still attempt to parse whatever stdout we have (some useful info may be printed)
                GLib.idle_add(self.parse_formats, stdout, stderr)
                return

            # success -> parse
            GLib.idle_add(self.parse_formats, stdout, stderr)

        except FileNotFoundError:
            self.log_error("yt-dlp", "yt-dlp binary not found. Install: pip install yt-dlp", {"cmd": "yt-dlp"})
        except Exception as e:
            tb = traceback.format_exc(limit=3)
            self.log_error("Fetch", "Unexpected error while fetching formats",
                           {"exception": str(e), "traceback": tb})
        finally:
            # Re-enable button and restore label on the main thread
            _safe_idle(self.fetch_btn.set_sensitive, True)
            _safe_idle(self.fetch_btn.set_label, "Fetch Formats")

    def parse_formats(self, stdout, stderr):
        """Parse yt-dlp format output"""
        self.available_formats.clear()
        try:
            self.v_format_combo.remove_all()
        except Exception:
            # ignore GUI removal errors
            pass

        try:
            # If stderr contains info, log it
            if stderr and stderr.strip():
                self.log_debug("yt-dlp", "stderr returned during format listing", {"stderr": stderr.strip()[:2000]})

            lines = stdout.splitlines()
            in_formats = False
            formats_found = 0

            for line in lines:
                lower = line.lower()
                if "format code" in lower or line.strip().lower().startswith("format code"):
                    in_formats = True
                    continue

                if in_formats:
                    stripped = line.strip()
                    if not stripped:
                        # blank line may indicate end of formats table
                        continue
                    parts = stripped.split()
                    if len(parts) >= 1:
                        format_code = parts[0]
                        format_info = " ".join(parts[1:]) if len(parts) > 1 else ""
                        key = format_code
                        suffix = format_info[:60] + ("..." if len(format_info) > 60 else "")
                        # ensure unique keys (append suffix count if needed)
                        if key in self.available_formats:
                            # make unique - append a suffix
                            i = 1
                            while f"{key}_{i}" in self.available_formats:
                                i += 1
                            key = f"{key}_{i}"
                        self.available_formats[key] = format_info
                        try:
                            self.v_format_combo.append(key, f"{format_code} - {suffix}")
                        except Exception:
                            # ignore append GUI errors but keep memory entry
                            pass
                        formats_found += 1

            if formats_found:
                first_key = next(iter(self.available_formats.keys()))
                try:
                    self.v_format_combo.set_active_id(first_key)
                except Exception:
                    pass
                self.log_info("Parsing", f"Found {formats_found} available formats")
            else:
                # fallback: try to append 'best'
                self.log_warn("Parsing", "No formats found in yt-dlp output", {"stdout_len": len(stdout), "stderr_len": len(stderr)})
                try:
                    self.v_format_combo.append("best", "Unable to parse formats")
                    self.v_format_combo.set_active_id("best")
                except Exception:
                    pass
        except Exception as e:
            tb = traceback.format_exc(limit=3)
            self.log_error("Parsing", "Failed to parse formats", {"exception": str(e), "traceback": tb})
            try:
                self.v_format_combo.append("best", "Error fetching formats")
                self.v_format_combo.set_active_id("best")
            except Exception:
                pass

    def on_browse_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Download Location",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)

        if dialog.run() == Gtk.ResponseType.OK:
            self.location_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def _append_recent_output_debug(self):
        """Return a string with recent output lines for debugging."""
        try:
            return "\n".join(list(self._recent_output)[-200:])
        except Exception:
            return ""

    def on_clear_log(self, button):
        text_buffer = self.status_view.get_buffer()
        text_buffer.set_text("")
        self._recent_output.clear()

    def on_download_clicked(self, button):
        url = self.url_entry.get_text().strip()
        if not url:
            self.log_error("Input", "Please enter a URL")
            return

        # Validate URL minimally
        if not self._looks_like_url(url):
            self.log_error("Input", "URL does not look valid", {"url": url})
            return

        if self.type_combo.get_active_id() == "video" and not self.available_formats:
            self.log_warn("Usage", "No formats are available — fetching formats is recommended before downloading.")

        # Check yt-dlp presence
        if not shutil.which("yt-dlp"):
            self.log_error("yt-dlp", "yt-dlp not found on PATH. Install via: pip install yt-dlp")
            return

        self.download_thread = threading.Thread(target=self.start_download, args=(url,), daemon=True)
        self.download_thread.start()

    def on_cancel_clicked(self, button):
        if self.process:
            try:
                self.process.terminate()
                self.log_info("Process", "Sent terminate() to process")
            except Exception as e:
                self.log_warn("Process", "Failed to terminate gracefully; attempting kill", {"exception": str(e)})
                try:
                    self.process.kill()
                except Exception as e2:
                    self.log_error("Process", "Failed to kill process", {"exception": str(e2)})
            _safe_idle(self.log_info, "Process", "Download stop requested by user")
        else:
            self.log_warn("Process", "No active process to cancel")

    def build_cmd(self, url):
        """Build yt-dlp command based on settings"""
        cmd = ["yt-dlp"]

        cmd.extend([
            "--no-warnings",
            "-R", "10",
            "--socket-timeout", "30",
            "--extractor-args", "youtube:player_client=web,youtube:ignore_consent_challenge=true",
            "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        ])

        if self.playlist_check.get_active():
            cmd.append("-i")

        download_type = self.type_combo.get_active_id()
        location = self.location_entry.get_text() or str(Path.home() / "Downloads")

        if download_type == "audio":
            cmd.append("-x")
            audio_format = self.a_format_combo.get_active_id()
            if audio_format and audio_format != "best":
                cmd.extend(["--audio-format", audio_format])
            if self.thumbnail_check.get_active():
                cmd.append("--embed-thumbnail")
        else:
            # Use selected format from dropdown
            selected_format = self.v_format_combo.get_active_id()
            if selected_format:
                cmd.extend(["-f", selected_format])

        if self.subtitle_check.get_active():
            cmd.append("--write-subs")
            sub_lang = self.sub_lang_combo.get_active_id() or "en"
            cmd.extend(["--sub-langs", sub_lang])
            if self.embed_sub_check.get_active() and download_type == "video":
                cmd.append("--embed-subs")

        cmd.extend(["-o", os.path.join(location, "%(title)s.%(ext)s"), url])
        return cmd

    def start_download(self, url):
        self.log_info("Download", f"Starting download from: {url}")
        _safe_idle(self.progress_bar.set_fraction, 0.0)
        self._recent_output.clear()

        try:
            cmd = self.build_cmd(url)
            cmd_str = " ".join(cmd)
            self.log_debug("Download", "Command", {"cmd": cmd_str})

            # Start process
            # We'll combine stdout and stderr to a single stream (keeps live logging simple)
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, bufsize=1
            )

            has_error = False
            # Read stdout line-by-line and keep recent lines for debug
            for raw_line in self.process.stdout:
                if raw_line is None:
                    continue
                line = raw_line.rstrip()
                # keep recent lines
                self._recent_output.append(line)
                _safe_idle(self.log_info, "yt-dlp", line)
                # error heuristics
                low = line.lower()
                if low.startswith("error") or "error:" in low or "failed" in low:
                    has_error = True

                # Try parsing progress lines containing '%' and 'eta'
                if "%" in line and "eta" in low:
                    try:
                        # extract the last token like '12.3%' or '12%'
                        # fallback: find a token with '%' and strip it
                        tokens = line.split()
                        pct_token = None
                        for t in reversed(tokens):
                            if "%" in t:
                                pct_token = t
                                break
                        if pct_token:
                            # remove trailing non-digit chars
                            val = "".join(ch for ch in pct_token if (ch.isdigit() or ch == "." or ch == ","))
                            val = val.replace(",", ".")
                            percent = float(val)
                            _safe_idle(self.progress_bar.set_fraction, min(percent / 100.0, 1.0))
                    except Exception:
                        pass

            # wait and inspect return code
            rc = self.process.wait()
            recent_out = "\n".join(list(self._recent_output)[-200:])
            if rc == 0 and not has_error:
                _safe_idle(self.log_info, "Download", "[SUCCESS] Download completed!")
                _safe_idle(self.progress_bar.set_fraction, 1.0)
            else:
                debug = {"returncode": rc, "recent_output_tail": recent_out[-3000:]}
                self.log_error("Download", "[FAILED] Download encountered errors. Check recent output above.", debug)
                _safe_idle(self.progress_bar.set_fraction, 0.0)

        except FileNotFoundError:
            self.log_error("yt-dlp", "yt-dlp not found. Install: pip install yt-dlp", {"cmd": "yt-dlp"})
        except Exception as e:
            tb = traceback.format_exc(limit=5)
            self.log_error("Download", "Unexpected exception during download", {"exception": str(e), "traceback": tb})
        finally:
            # cleanup
            try:
                self.process = None
            except Exception:
                self.process = None

    def _looks_like_url(self, url):
        """Very-small heuristic to validate URL (not strict)."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            if not parsed.netloc:
                return False
            return True
        except Exception:
            return False

# ---------- Application ----------
class YtDlpApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.xfce.ytdlp")
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = YtDlpGUI(self)
        self.window.present()


if __name__ == "__main__":
    app = YtDlpApp()
    app.run(sys.argv)
