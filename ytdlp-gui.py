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
        self.all_formats = []
        self.is_video_mode = True

        self.setup_ui()

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
        self.type_combo = Gtk.ComboBoxText()
        self.type_combo.append("video", "Video")
        self.type_combo.append("audio", "Audio Only")
        self.type_combo.set_active_id("video")
        self.type_combo.connect("changed", self.on_type_changed)
        main_box.pack_start(type_label, False, False, 0)
        main_box.pack_start(self.type_combo, False, False, 0)

        # Format dropdown
        fmt_label = Gtk.Label(label="Available Formats:", xalign=0)
        self.format_combo = Gtk.ComboBoxText()
        self.format_combo.append("none", "Fetch a URL first...")
        self.format_combo.set_active_id("none")
        main_box.pack_start(fmt_label, False, False, 0)
        main_box.pack_start(self.format_combo, False, False, 0)

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

        # Progress + log
        progress_label = Gtk.Label(label="Progress:", xalign=0)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.status_view = Gtk.TextView(editable=False)
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

    def log_status(self, message, replace_last=False):
        buf = self.status_view.get_buffer()
        if replace_last:
            start = buf.get_iter_at_line(buf.get_line_count() - 1)
            end = buf.get_end_iter()
            buf.delete(start, end)
        end = buf.get_end_iter()
        buf.insert(end, message + "\n")
        self.status_view.scroll_to_iter(buf.get_end_iter(), 0.0, True, 0.0, 1.0)

    def on_type_changed(self, combo):
        self.is_video_mode = combo.get_active_id() == "video"

    def on_fetch_formats(self, button):
        url = self.url_entry.get_text().strip()
        if not url:
            self.log_status("[ERROR] Please enter a URL.")
            return

        self.fetch_btn.set_sensitive(False)
        self.fetch_btn.set_label("Fetching...")
        self.format_combo.remove_all()
        self.format_combo.append("loading", "Fetching formats...")
        self.format_combo.set_active_id("loading")

        threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True).start()

    def fetch_formats_thread(self, url):
        cmd = ["yt-dlp", "--list-formats", url]
        GLib.idle_add(self.log_status, f"[CMD] {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            stdout, stderr = result.stdout, result.stderr

            if stderr.strip():
                GLib.idle_add(self.log_status, f"[yt-dlp][stderr] {stderr.strip()}")

            if not stdout.strip():
                GLib.idle_add(self.log_status, "[WARN] No output received from yt-dlp")
                return

            formats = self.parse_formats(stdout)
            self.all_formats = formats
            GLib.idle_add(self.update_format_dropdown)
            GLib.idle_add(self.log_status, f"[INFO] Found {len(formats)} formats")

        except subprocess.TimeoutExpired:
            GLib.idle_add(self.log_status, "[ERROR] Timeout fetching formats")
        except Exception as e:
            GLib.idle_add(self.log_status, f"[ERROR][FetchThread] {e}")
        finally:
            GLib.idle_add(self.fetch_btn.set_sensitive, True)
            GLib.idle_add(self.fetch_btn.set_label, "Fetch Formats")

    def parse_formats(self, text):
        formats = []
        pattern = re.compile(r"^(?P<id>[0-9a-zA-Z\-_]+)\s+(?P<ext>\w+)\s+(?P<details>.+)$")
        for line in text.splitlines():
            m = pattern.match(line.strip())
            if not m:
                continue
            fmt_id = m.group("id")
            ext = m.group("ext")
            details = m.group("details")
            label = f"{fmt_id} - {ext.upper()} - {details}"
            formats.append({"id": fmt_id, "label": label})
        return formats

    def update_format_dropdown(self):
        self.format_combo.remove_all()

        if not self.all_formats:
            self.format_combo.append("none", "No formats found")
            self.format_combo.set_active_id("none")
            return

        for f in self.all_formats:
            self.format_combo.append(f["id"], f["label"])
        self.format_combo.set_active(0)

    def on_download_clicked(self, button):
        url = self.url_entry.get_text().strip()
        if not url:
            self.log_status("[ERROR] Please enter a URL before downloading.")
            return
        threading.Thread(target=self.download_thread_fn, args=(url,), daemon=True).start()

    def build_download_cmd(self, url):
        cmd = ["yt-dlp"]
        loc = self.location_entry.get_text().strip() or str(Path.home() / "Downloads")
        fmt_id = self.format_combo.get_active_id()
        if fmt_id and fmt_id not in ("none", "loading"):
            cmd += ["-f", fmt_id]

        if not self.is_video_mode:
            cmd += ["--extract-audio"]

        cmd += ["-o", os.path.join(loc, "%(title)s.%(ext)s"), url]
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
                clean = line.strip()
                if "%" in clean and "ETA" in clean:
                    try:
                        percent = float(re.search(r"(\d+(?:\.\d+)?)%", clean).group(1))
                        GLib.idle_add(self.progress_bar.set_fraction, min(percent / 100, 1.0))
                        GLib.idle_add(self.log_status, clean, True)
                    except Exception:
                        GLib.idle_add(self.log_status, clean)
                else:
                    GLib.idle_add(self.log_status, clean)

            self.process.wait()
            if self.process.returncode == 0:
                GLib.idle_add(self.log_status, "[SUCCESS] Download complete.")
                GLib.idle_add(self.progress_bar.set_fraction, 1.0)
            else:
                GLib.idle_add(self.log_status, f"[FAILED] Exit code {self.process.returncode}")
        except Exception as e:
            GLib.idle_add(self.log_status, f"[ERROR] {e}")
        finally:
            self.process = None

    def on_browse_clicked(self, button):
        dlg = Gtk.FileChooserDialog(
            title="Select Download Location", parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        if dlg.run() == Gtk.ResponseType.OK:
            self.location_entry.set_text(dlg.get_filename())
        dlg.destroy()

    def on_clear_log(self, button):
        self.status_view.get_buffer().set_text("")

    def on_cancel_clicked(self, button):
        if self.process:
            try:
                self.process.terminate()
                self.log_status("[CANCELLED] Download stopped by user")
            except Exception as e:
                self.log_status(f"[ERROR][Cancel] {e}")


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