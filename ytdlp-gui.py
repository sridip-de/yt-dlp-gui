#!/usr/bin/env python3
import gi
import threading
import subprocess
import os
import sys
import re
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib


class YtDlpGUI(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="yt-dlp GUI Wrapper")
        self.set_default_size(900, 700)
        self.set_border_width(10)

        self.process = None
        self.all_formats = []
        self.is_video_mode = True

        self.setup_ui()

    def setup_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(main_box)

        # URL and fetch
        url_row = Gtk.Box(spacing=6)
        url_label = Gtk.Label(label="URL:", xalign=0)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text("Enter YouTube URL...")
        self.fetch_btn = Gtk.Button(label="Fetch Formats")
        self.fetch_btn.connect("clicked", self.on_fetch_formats)
        url_row.pack_start(url_label, False, False, 0)
        url_row.pack_start(self.url_entry, True, True, 0)
        url_row.pack_start(self.fetch_btn, False, False, 0)
        main_box.pack_start(url_row, False, False, 0)

        # Type selection (affects download behavior only)
        type_row = Gtk.Box(spacing=6)
        type_label = Gtk.Label(label="Download Type:", xalign=0)
        self.type_combo = Gtk.ComboBoxText()
        self.type_combo.append("video", "Video")
        self.type_combo.append("audio", "Audio Only")
        self.type_combo.set_active_id("video")
        self.type_combo.connect("changed", self.on_type_changed)
        type_row.pack_start(type_label, False, False, 0)
        type_row.pack_start(self.type_combo, False, False, 0)
        main_box.pack_start(type_row, False, False, 0)

        # Format dropdown (will show all formats EXCEPT video-only)
        fmt_label = Gtk.Label(label="Available Formats (video-only excluded):", xalign=0)
        self.format_combo = Gtk.ComboBoxText()
        self.format_combo.append("none", "Fetch a URL first...")
        self.format_combo.set_active_id("none")
        main_box.pack_start(fmt_label, False, False, 0)
        main_box.pack_start(self.format_combo, False, False, 0)

        # Download location and options
        loc_row = Gtk.Box(spacing=6)
        loc_label = Gtk.Label(label="Output folder:", xalign=0)
        self.loc_entry = Gtk.Entry()
        self.loc_entry.set_text(str(Path.home() / "Downloads"))
        browse_btn = Gtk.Button(label="Browse")
        browse_btn.connect("clicked", self.on_browse_clicked)
        loc_row.pack_start(loc_label, False, False, 0)
        loc_row.pack_start(self.loc_entry, True, True, 0)
        loc_row.pack_start(browse_btn, False, False, 0)
        main_box.pack_start(loc_row, False, False, 0)

        opts_row = Gtk.Box(spacing=6)
        self.subs_check = Gtk.CheckButton(label="Download subtitles (--write-subs)")
        self.embed_sub = Gtk.CheckButton(label="Embed subtitles (--embed-subs)")
        self.playlist_check = Gtk.CheckButton(label="Playlist (-i)")
        self.thumb_check = Gtk.CheckButton(label="Embed thumbnail (audio)")
        opts_row.pack_start(self.subs_check, False, False, 0)
        opts_row.pack_start(self.embed_sub, False, False, 0)
        opts_row.pack_start(self.playlist_check, False, False, 0)
        opts_row.pack_start(self.thumb_check, False, False, 0)
        main_box.pack_start(opts_row, False, False, 0)

        # Progress and status log
        progress_label = Gtk.Label(label="Progress:", xalign=0)
        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        self.status_view = Gtk.TextView()
        self.status_view.set_editable(False)
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(-1, 300)
        scroll.add(self.status_view)
        main_box.pack_start(progress_label, False, False, 0)
        main_box.pack_start(self.progress, False, False, 0)
        main_box.pack_start(scroll, True, True, 0)

        # Buttons
        btn_row = Gtk.Box(spacing=6)
        download_btn = Gtk.Button(label="Download")
        download_btn.connect("clicked", self.on_download_clicked)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_cancel_clicked)
        clear_btn = Gtk.Button(label="Clear Log")
        clear_btn.connect("clicked", self.on_clear_log)
        btn_row.pack_start(download_btn, True, True, 0)
        btn_row.pack_start(cancel_btn, True, True, 0)
        btn_row.pack_start(clear_btn, True, True, 0)
        main_box.pack_start(btn_row, False, False, 0)

        self.show_all()

    # ---------- Logging helpers ----------
    def log_status(self, text, replace_last=False):
        buf = self.status_view.get_buffer()
        if replace_last and buf.get_line_count() > 0:
            try:
                start = buf.get_iter_at_line(buf.get_line_count() - 1)
                end = buf.get_end_iter()
                buf.delete(start, end)
            except Exception:
                # fallback: append instead
                pass
        end = buf.get_end_iter()
        buf.insert(end, text + "\n")
        self.status_view.scroll_to_iter(buf.get_end_iter(), 0.0, True, 0.0, 1.0)

    def on_clear_log(self, btn):
        self.status_view.get_buffer().set_text("")

    # ---------- Fetch formats (exact CLI) ----------
    def on_fetch_formats(self, btn):
        url = self.url_entry.get_text().strip()
        if not url:
            self.log_status("[ERROR] Please enter a URL.")
            return

        if not shutil_which("yt-dlp"):
            self.log_status("[ERROR] yt-dlp not found on PATH. Install with: pip install -U yt-dlp")
            return

        self.fetch_btn.set_sensitive(False)
        self.fetch_btn.set_label("Fetching...")
        self.format_combo.remove_all()
        self.format_combo.append("loading", "Fetching formats...")
        self.format_combo.set_active_id("loading")

        threading.Thread(target=self._fetch_formats_thread, args=(url,), daemon=True).start()

    def _fetch_formats_thread(self, url):
        cmd = ["yt-dlp", "--list-formats", url]
        GLib.idle_add(self.log_status, f"[CMD] {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            if stderr.strip():
                GLib.idle_add(self.log_status, f"[yt-dlp][stderr] {stderr.strip()}")
            if not stdout.strip():
                GLib.idle_add(self.log_status, "[WARN] yt-dlp returned no stdout.")
                return

            parsed = self._parse_formats(stdout)
            # filter out video-only formats here
            parsed_filtered = [p for p in parsed if not p.get("video_only", False)]
            self.all_formats = parsed_filtered
            GLib.idle_add(self.update_format_dropdown)
            GLib.idle_add(self.log_status, f"[INFO] Parsed {len(parsed)} formats, {len(parsed_filtered)} kept (video-only removed)")
        except subprocess.TimeoutExpired:
            GLib.idle_add(self.log_status, "[ERROR] Timeout while running yt-dlp --list-formats")
        except Exception as e:
            GLib.idle_add(self.log_status, f"[ERROR] Exception while fetching formats: {e}")
        finally:
            GLib.idle_add(self.fetch_btn.set_sensitive, True)
            GLib.idle_add(self.fetch_btn.set_label, "Fetch Formats")

    # ---------- Format parsing ----------
    def _parse_formats(self, text):
        """
        Best-effort parse of `yt-dlp --list-formats` table lines.
        Returns list of dicts: {id, ext, label, video_only(bool), raw_line}
        """
        formats = []
        # Common pattern: "<id>  <EXT> - ..." or "<id>  <description...>"
        # We'll parse line-start token as id, then remainder as text to inspect.
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            # skip header lines
            if re.search(r"format code", line, re.IGNORECASE):
                continue
            # try to match an initial token that looks like a format id
            m = re.match(r"^(?P<id>[0-9A-Za-z_\-+]+)\s+(?P<rest>.+)$", line)
            if not m:
                continue
            fid = m.group("id")
            rest = m.group("rest").strip()

            # Determine extension if present as first token in rest
            ext_match = re.match(r"^(?P<ext>[A-Za-z0-9]+)\b", rest)
            ext = ext_match.group("ext") if ext_match else ""

            # Flag video-only: look for explicit markers like 'video only', 'video-only', 'videoonly'
            video_only = False
            if re.search(r"\bvideo only\b", rest, re.IGNORECASE) or \
               re.search(r"\bvideo-only\b", rest, re.IGNORECASE) or \
               re.search(r"\bvideoonly\b", rest, re.IGNORECASE):
                video_only = True

            # Also heuristic: lines that contain 'video' but not 'audio' and have resolution likely video-only
            low = rest.lower()
            if not video_only:
                if ("video" in low and "audio" not in low) and re.search(r"\b\d{2,4}p\b", low):
                    video_only = True

            label = f"{fid} - {rest}"
            formats.append({"id": fid, "ext": ext, "label": label, "video_only": video_only, "raw": line})
        return formats

    def update_format_dropdown(self):
        # Update dropdown on GUI thread
        try:
            self.format_combo.remove_all()
        except Exception:
            pass

        if not self.all_formats:
            self.format_combo.append("none", "No formats (or filtered out video-only)")
            try:
                self.format_combo.set_active_id("none")
            except Exception:
                pass
            return

        # Optionally: sort by human-friendly priority (best, resolution, etc.)
        def sort_key(f):
            # place 'best' at top, then by resolution if present
            key1 = 0 if f["id"].lower() == "best" else 1
            res_m = re.search(r"(\d{3,4})p", f["label"])
            key2 = -(int(res_m.group(1)) if res_m else 0)
            return (key1, key2, f["id"])

        try:
            self.all_formats.sort(key=sort_key)
        except Exception:
            pass

        for f in self.all_formats:
            self.format_combo.append(f["id"], f["label"])
        try:
            self.format_combo.set_active(0)
        except Exception:
            pass

    # ---------- Download ----------
    def on_download_clicked(self, btn):
        url = self.url_entry.get_text().strip()
        if not url:
            self.log_status("[ERROR] Enter a URL to download.")
            return

        if not shutil_which("yt-dlp"):
            self.log_status("[ERROR] yt-dlp not found on PATH. Install: pip install -U yt-dlp")
            return

        threading.Thread(target=self._download_thread, args=(url,), daemon=True).start()

    def _build_cmd(self, url):
        cmd = ["yt-dlp"]
        fid = self.format_combo.get_active_id()
        if fid and fid not in ("none", "loading"):
            cmd += ["-f", fid]

        if self.type_combo.get_active_id() == "audio":
            # use exact CLI flag for audio extraction
            cmd += ["-x"]

        if self.playlist_check.get_active():
            cmd += ["-i"]
        if self.subs_check.get_active():
            cmd += ["--write-subs"]
            # language selection could be added later
        if self.embed_sub.get_active():
            cmd += ["--embed-subs"]
        if self.thumb_check.get_active() and self.type_combo.get_active_id() == "audio":
            cmd += ["--embed-thumbnail"]

        outdir = self.loc_entry.get_text().strip() or str(Path.home() / "Downloads")
        cmd += ["-o", os.path.join(outdir, "%(title)s.%(ext)s"), url]
        return cmd

    def _download_thread(self, url):
        cmd = self._build_cmd(url)
        GLib.idle_add(self.log_status, f"[CMD] {' '.join(cmd)}")
        GLib.idle_add(self.progress.set_fraction, 0.0)

        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
        except FileNotFoundError:
            GLib.idle_add(self.log_status, "[ERROR] yt-dlp not found.")
            return
        except Exception as e:
            GLib.idle_add(self.log_status, f"[ERROR] Failed to start process: {e}")
            return

        # Stream lines and update progress inline
        for raw in self.process.stdout:
            line = raw.rstrip()
            # if progress-like: show in single line (replace_last=True)
            if "%" in line and ("ETA" in line or "eta" in line):
                # try extract percent
                m = re.search(r"(\d{1,3}(?:\.\d+)?)\%", line)
                if m:
                    try:
                        pct = float(m.group(1)) / 100.0
                        GLib.idle_add(self.progress.set_fraction, min(pct, 1.0))
                    except Exception:
                        pass
                GLib.idle_add(self.log_status, line, True)
            else:
                GLib.idle_add(self.log_status, line)

        rc = self.process.wait()
        if rc == 0:
            GLib.idle_add(self.log_status, "[SUCCESS] Download completed.")
            GLib.idle_add(self.progress.set_fraction, 1.0)
        else:
            GLib.idle_add(self.log_status, f"[FAILED] Exit code {rc}")

        self.process = None

    def on_cancel_clicked(self, btn):
        if self.process:
            try:
                self.process.terminate()
                self.log_status("[ACTION] Sent terminate() to process")
            except Exception as e:
                self.log_status(f"[ERROR] Failed to terminate: {e}")
        else:
            self.log_status("[INFO] No active process to cancel")

    def on_browse_clicked(self, btn):
        dlg = Gtk.FileChooserDialog(
            title="Select Download Location", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            self.loc_entry.set_text(dlg.get_filename())
        dlg.destroy()


# small helper for yt-dlp presence
def shutil_which(name):
    # avoid importing shutil repeatedly; implement small which
    from shutil import which
    return which(name)


class YtDlpApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.xfce.ytdlpwrapper")
        self.window = None

    def do_activate(self):
        if not self.window:
            self.window = YtDlpGUI(self)
        self.window.present()


if __name__ == "__main__":
    app = YtDlpApp()
    app.run(sys.argv)
