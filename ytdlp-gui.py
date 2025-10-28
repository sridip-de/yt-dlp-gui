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
        self.set_default_size(800, 900)
        self.set_border_width(10)

        self.process = None
        self.download_thread = None
        self.available_formats = {}
        self.is_video_mode = True
        self.all_formats = []  # Store all fetched formats

        self.setup_ui()

    # ---------------- UI SETUP ----------------
    def setup_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_box)

        # URL input
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

        # Type selection
        type_label = Gtk.Label(label="Download Type:", xalign=0)
        type_box = Gtk.Box(spacing=10)
        self.type_combo = Gtk.ComboBoxText()
        self.type_combo.append("video", "Video")
        self.type_combo.append("audio", "Audio Only")
        self.type_combo.set_active_id("video")
        self.type_combo.connect("changed", self.on_type_changed)
        type_box.pack_start(self.type_combo, False, False, 0)
        main_box.pack_start(type_label, False, False, 0)
        main_box.pack_start(type_box, False, False, 0)

        # Format selection
        fmt_label = Gtk.Label(label="Available Formats:", xalign=0)
        self.v_format_combo = Gtk.ComboBoxText()
        self.v_format_combo.append("none", "Fetch a URL first...")
        self.v_format_combo.set_active_id("none")
        main_box.pack_start(fmt_label, False, False, 0)
        main_box.pack_start(self.v_format_combo, False, False, 0)

        # Download location
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

        # Subtitles / playlist checkboxes
        opt_box = Gtk.Box(spacing=10)
        self.subs_check = Gtk.CheckButton(label="Download Subtitles")
        self.embed_check = Gtk.CheckButton(label="Embed Subtitles")
        self.playlist_check = Gtk.CheckButton(label="Download Playlist")
        self.thumb_check = Gtk.CheckButton(label="Embed Thumbnail (Audio only)")
        opt_box.pack_start(self.subs_check, False, False, 0)
        opt_box.pack_start(self.embed_check, False, False, 0)
        opt_box.pack_start(self.playlist_check, False, False, 0)
        opt_box.pack_start(self.thumb_check, False, False, 0)
        main_box.pack_start(opt_box, False, False, 0)

        # Progress + log area
        progress_label = Gtk.Label(label="Progress:", xalign=0)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.status_view = Gtk.TextView()
        self.status_view.set_editable(False)
        scroll_win = Gtk.ScrolledWindow()
        scroll_win.set_size_request(-1, 250)
        scroll_win.add(self.status_view)
        main_box.pack_start(progress_label, False, False, 0)
        main_box.pack_start(self.progress_bar, False, False, 0)
        main_box.pack_start(scroll_win, True, True, 0)

        # Buttons
        btn_box = Gtk.Box(spacing=10)
        self.download_btn = Gtk.Button(label="Download")
        self.download_btn.connect("clicked", self.on_download_clicked)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_cancel_clicked)
        clear_btn = Gtk.Button(label="Clear Log")
        clear_btn.connect("clicked", self.on_clear_log)
        btn_box.pack_start(self.download_btn, True, True, 0)
        btn_box.pack_start(cancel_btn, True, True, 0)
        btn_box.pack_start(clear_btn, True, True, 0)
        main_box.pack_start(btn_box, False, False, 0)

        self.show_all()

    # ---------------- EVENT HANDLERS ----------------
    def on_type_changed(self, combo):
        """Update dropdown when type changes"""
        self.is_video_mode = combo.get_active_id() == "video"
        self.update_format_dropdown_by_type()

    def update_format_dropdown_by_type(self):
        """Filter and update dropdown based on selected type"""
        self.v_format_combo.remove_all()
        
        if not self.all_formats:
            self.v_format_combo.append("none", "Fetch a URL first...")
            self.v_format_combo.set_active_id("none")
            return
        
        if self.is_video_mode:
            filtered = [fmt for fmt in self.all_formats if fmt['type'] == 'video']
            label_text = "Video Formats"
        else:
            filtered = [fmt for fmt in self.all_formats if fmt['type'] == 'audio']
            label_text = "Audio Formats"
        
        if not filtered:
            self.v_format_combo.append("none", f"No {label_text.lower()} found")
            self.v_format_combo.set_active_id("none")
            return
        
        for fmt in filtered:
            self.v_format_combo.append(fmt['id'], fmt['label'])
        self.v_format_combo.set_active(0)

    def on_browse_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Download Location",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                           Gtk.STOCK_OK, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.location_entry.set_text(dialog.get_filename())
        dialog.destroy()

    def on_clear_log(self, button):
        buf = self.status_view.get_buffer()
        buf.set_text("")

    def on_cancel_clicked(self, button):
        if self.process:
            try:
                self.process.terminate()
                self.log_status("[CANCELLED] Download stopped by user")
            except Exception as e:
                self.log_status(f"[ERROR][Cancel] {e}")

    def log_status(self, message, replace_last=False):
        buf = self.status_view.get_buffer()
        if replace_last:
            # Remove last line and replace it
            end = buf.get_end_iter()
            start = buf.get_iter_at_line(buf.get_line_count() - 1)
            buf.delete(start, end)
        end = buf.get_end_iter()
        buf.insert(end, message + "\n")
        self.status_view.scroll_to_iter(buf.get_end_iter(), 0.0, True, 0.0, 1.0)

    # ---------------- FORMAT FETCHING ----------------
    def on_fetch_formats(self, button):
        url = self.url_entry.get_text().strip()
        if not url:
            self.show_error("Please enter a URL.")
            return

        self.fetch_btn.set_sensitive(False)
        self.fetch_btn.set_label("Fetching...")
        self.v_format_combo.remove_all()
        self.v_format_combo.append("loading", "Fetching formats...")
        self.v_format_combo.set_active_id("loading")

        t = threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True)
        t.start()

    def fetch_formats_thread(self, url):
        cmd = ["yt-dlp", "--list-formats", url]
        GLib.idle_add(self.log_status, f"[CMD] {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            stdout, stderr = result.stdout, result.stderr

            if stderr.strip():
                GLib.idle_add(self.log_status, f"[yt-dlp][stderr] {stderr.strip()}")
            if not stdout.strip():
                GLib.idle_add(self.log_status, "[WARN] No output received from yt-dlp")
                return

            parsed = self.parse_formats(stdout)
            self.all_formats = parsed
            GLib.idle_add(self.update_format_dropdown_by_type)
            GLib.idle_add(self.log_status, f"[INFO] Found {len(parsed)} total formats")

        except subprocess.TimeoutExpired:
            GLib.idle_add(self.log_status, "[ERROR] Timeout fetching formats")
        except FileNotFoundError:
            GLib.idle_add(self.log_status, "[ERROR] yt-dlp not found (install with pip)")
        except Exception as e:
            GLib.idle_add(self.log_status, f"[ERROR][FetchThread] {e}")
        finally:
            GLib.idle_add(self.fetch_btn.set_sensitive, True)
            GLib.idle_add(self.fetch_btn.set_label, "Fetch Formats")

    def parse_formats(self, output):
        """
        Parse yt-dlp --list-formats output with robust format detection.
        Returns list of dicts with keys: id, label, type (video/audio)
        """
        lines = output.splitlines()
        formats = []
        in_format_section = False
        
        for line in lines:
            # Look for the format header line
            if "format code" in line.lower() or "ID" in line and "EXT" in line:
                in_format_section = True
                continue
            
            if not in_format_section or not line.strip():
                continue
            
            # Skip lines that don't start with format codes (usually end up being description lines)
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # Try to parse format line
            # Format: ID  EXT  RESOLUTION FPS CH   FILESIZE   TBR  PROTO  VCODEC  ACODEC  MORE INFO
            parts = line_stripped.split()
            
            if len(parts) < 2:
                continue
            
            fmt_id = parts[0]
            
            # Skip non-format lines (IDs are typically numbers or common codes like "best", "worst")
            # But we want to include those too
            if not (fmt_id[0].isdigit() or fmt_id in ["best", "worst", "bestvideo", "bestaudio"]):
                # Try alternative: might be a description line, skip it
                if not re.match(r'^[0-9a-zA-Z_]+$', fmt_id):
                    continue
            
            ext = parts[1] if len(parts) > 1 else "unknown"
            
            # Determine format type based on description content
            fmt_type = self.determine_format_type(line_stripped)
            
            if fmt_type is None:
                continue
            
            # Create readable label
            label = f"{fmt_id} - {ext.upper()}"
            
            # Add resolution/bitrate info if available
            for i, part in enumerate(parts[2:6]):
                if part and part[0].isdigit():
                    label += f" - {part}"
            
            formats.append({
                'id': fmt_id,
                'label': label,
                'type': fmt_type,
                'ext': ext
            })
        
        return formats

    def determine_format_type(self, line):
        """
        Determine if format is video or audio based on line content.
        """
        line_lower = line.lower()
        
        # Look for audio indicators
        if "audio only" in line_lower:
            return "audio"
        
        # Look for video indicators
        if any(x in line_lower for x in ["1080p", "720p", "480p", "360p", "240p", "144p", "x"]):
            return "video"
        
        # Check for codec indicators
        if "vp9" in line_lower or "h.264" in line_lower or "h264" in line_lower or "avc" in line_lower:
            return "video"
        
        if "opus" in line_lower or "aac" in line_lower or "vorbis" in line_lower or "mp3" in line_lower:
            return "audio"
        
        # Check for video/audio keywords in description
        if "video" in line_lower and "audio" not in line_lower:
            return "video"
        if "audio" in line_lower:
            return "audio"
        
        # Default: if it has high numbers, likely video
        if re.search(r'\d{3,4}x\d{3,4}', line):  # resolution pattern
            return "video"
        
        return None

    # ---------------- DOWNLOAD ----------------
    def on_download_clicked(self, button):
        url = self.url_entry.get_text().strip()
        if not url:
            self.show_error("Please enter a URL before downloading.")
            return

        self.download_thread = threading.Thread(target=self.download_thread_fn, args=(url,), daemon=True)
        self.download_thread.start()

    def build_download_cmd(self, url):
        cmd = ["yt-dlp"]
        location = self.location_entry.get_text().strip() or str(Path.home() / "Downloads")

        fmt_id = self.v_format_combo.get_active_id()
        if fmt_id and fmt_id not in ("none", "loading"):
            cmd += ["-f", fmt_id]

        if self.subs_check.get_active():
            cmd.append("--write-subs")
        if self.embed_check.get_active():
            cmd.append("--embed-subs")
        if self.playlist_check.get_active():
            cmd.append("-i")

        if not self.is_video_mode and self.thumb_check.get_active():
            cmd.append("--embed-thumbnail")

        cmd += ["-o", os.path.join(location, "%(title)s.%(ext)s"), url]
        return cmd

    def download_thread_fn(self, url):
        cmd = self.build_download_cmd(url)
        GLib.idle_add(self.log_status, f"[CMD] {' '.join(cmd)}")
        GLib.idle_add(self.progress_bar.set_fraction, 0.0)

        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, bufsize=1
            )

            for line in self.process.stdout:
                if "%" in line and "ETA" in line:
                    try:
                        percent = float(line.split("%")[0].split()[-1])
                        GLib.idle_add(self.progress_bar.set_fraction, min(percent / 100, 1.0))
                        GLib.idle_add(self.log_status, line.rstrip(), True)
                    except Exception:
                        GLib.idle_add(self.log_status, line.rstrip())
                else:
                    GLib.idle_add(self.log_status, line.rstrip())

            self.process.wait()
            if self.process.returncode == 0:
                GLib.idle_add(self.log_status, "[SUCCESS] Download complete.")
                GLib.idle_add(self.progress_bar.set_fraction, 1.0)
            else:
                GLib.idle_add(self.log_status, f"[FAILED] Return code {self.process.returncode}")

        except FileNotFoundError:
            GLib.idle_add(self.log_status, "[ERROR] yt-dlp not found.")
        except Exception as e:
            GLib.idle_add(self.log_status, f"[ERROR][DownloadThread] {e}")
        finally:
            self.process = None

    def show_error(self, msg):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=msg,
        )
        dlg.run()
        dlg.destroy()
        self.log_status(f"[ERROR] {msg}")


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