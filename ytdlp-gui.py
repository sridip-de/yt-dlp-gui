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
        self.all_formats = []
        self.log_visible = True
        self.window_expanded_height = 900

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

        # Options
        opt_box = Gtk.Box(spacing=10)
        self.subs_check = Gtk.CheckButton(label="Download Subtitles")
        self.embed_check = Gtk.CheckButton(label="Embed Subtitles")
        self.subs_check.connect("toggled", self.on_subs_toggled)
        self.embed_check.connect("toggled", self.on_embed_subs_toggled)
        
        self.playlist_check = Gtk.CheckButton(label="Download Playlist")
        
        self.thumb_check = Gtk.CheckButton(label="Embed Thumbnail (Audio only)")
        self.thumb_check.connect("toggled", self.on_thumb_toggled)
        
        opt_box.pack_start(self.subs_check, False, False, 0)
        opt_box.pack_start(self.embed_check, False, False, 0)
        opt_box.pack_start(self.playlist_check, False, False, 0)
        opt_box.pack_start(self.thumb_check, False, False, 0)
        main_box.pack_start(opt_box, False, False, 0)

        # Buttons above log box
        btn_box = Gtk.Box(spacing=10)
        self.download_btn = Gtk.Button(label="Download")
        self.download_btn.connect("clicked", self.on_download_clicked)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_cancel_clicked)
        clear_btn = Gtk.Button(label="Clear Log")
        clear_btn.connect("clicked", self.on_clear_log)
        self.toggle_log_btn = Gtk.Button(label="Hide Log")
        self.toggle_log_btn.connect("clicked", self.on_toggle_log)

        btn_box.pack_start(self.download_btn, True, True, 0)
        btn_box.pack_start(cancel_btn, True, True, 0)
        btn_box.pack_start(clear_btn, True, True, 0)
        btn_box.pack_start(self.toggle_log_btn, True, True, 0)
        main_box.pack_start(btn_box, False, False, 0)

        # Log box (progress + logs)
        self.log_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        progress_label = Gtk.Label(label="Progress:", xalign=0)
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        self.status_view = Gtk.TextView()
        self.status_view.set_editable(False)
        scroll_win = Gtk.ScrolledWindow()
        scroll_win.set_size_request(-1, 250)
        scroll_win.add(self.status_view)
        self.log_box.pack_start(progress_label, False, False, 0)
        self.log_box.pack_start(self.progress_bar, False, False, 0)
        self.log_box.pack_start(scroll_win, True, True, 0)
        main_box.pack_start(self.log_box, True, True, 0)

        self.show_all()

    # ----- UI event handlers -----
    def on_type_changed(self, combo):
        self.is_video_mode = combo.get_active_id() == "video"
        mode_str = "Video" if self.is_video_mode else "Audio Only"
        self.log_status(f"[MODE] Switched to {mode_str} mode")
        
        # Disable thumbnail checkbox in video mode, enable in audio mode
        self.thumb_check.set_sensitive(not self.is_video_mode)
        
        # Update format dropdown to show appropriate formats
        if self.all_formats:
            self.update_format_dropdown()

    def on_subs_toggled(self, widget):
        state = "enabled" if widget.get_active() else "disabled"
        self.log_status(f"[SUBS] Subtitle download {state}")

    def on_embed_subs_toggled(self, widget):
        if widget.get_active():
            if not self.subs_check.get_active():
                self.log_status("[SUBS] Subtitle embedding enabled (download will be automatic)")
                self.subs_check.set_active(True)
            else:
                self.log_status("[SUBS] Subtitle embedding enabled")
        else:
            self.log_status("[SUBS] Subtitle embedding disabled")

    def on_thumb_toggled(self, widget):
        if not self.is_video_mode:
            state = "enabled" if widget.get_active() else "disabled"
            self.log_status(f"[THUMB] Thumbnail embedding {state}")
        else:
            self.log_status("[THUMB] Thumbnail embedding only available in Audio mode")
            widget.set_active(False)

    def on_toggle_log(self, button):
        self.log_visible = not self.log_visible
        self.log_box.set_visible(self.log_visible)
        button.set_label("Hide Log" if self.log_visible else "Show Log")
        
        # Smoothly resize the window
        current_width, current_height = self.get_size()
        if self.log_visible:
            # Expand: restore to expanded height
            new_height = self.window_expanded_height
            self.resize(current_width, new_height)
        else:
            # Collapse: shrink window
            self.window_expanded_height = current_height
            self.resize(current_width, 400)
        
        self.log_status(f"[UI] Log panel {'shown' if self.log_visible else 'hidden'}")

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
        self.log_status("[LOG] Cleared")

    def on_cancel_clicked(self, button):
        if self.process:
            try:
                self.process.terminate()
                self.log_status("[CANCELLED] Download stopped by user")
            except Exception as e:
                self.log_status("[ERROR][Cancel] " + str(e))

    def log_status(self, message, replace_last=False):
        buf = self.status_view.get_buffer()
        if replace_last:
            end = buf.get_end_iter()
            start = buf.get_iter_at_line(buf.get_line_count() - 1)
            buf.delete(start, end)
        end = buf.get_end_iter()
        buf.insert(end, message + "\n")
        self.status_view.scroll_to_iter(buf.get_end_iter(), 0.0, True, 0.0, 1.0)

    # ----- Fetch formats -----
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
        GLib.idle_add(self.log_status, "[CMD] " + " ".join(cmd))
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            stdout, stderr = result.stdout, result.stderr

            if stderr.strip():
                GLib.idle_add(self.log_status, "[yt-dlp][stderr] " + stderr.strip())
            if not stdout.strip():
                GLib.idle_add(self.log_status, "[WARN] No output received from yt-dlp")
                return

            parsed = self.parse_formats(stdout)
            self.all_formats = parsed
            GLib.idle_add(self.update_format_dropdown)
            GLib.idle_add(self.log_status, "[INFO] Found " + str(len(parsed)) + " formats")

        except subprocess.TimeoutExpired:
            GLib.idle_add(self.log_status, "[ERROR] Timeout fetching formats")
        except FileNotFoundError:
            GLib.idle_add(self.log_status, "[ERROR] yt-dlp not found (install with pip)")
        except Exception as e:
            GLib.idle_add(self.log_status, "[ERROR][FetchThread] " + str(e))
        finally:
            GLib.idle_add(self.fetch_btn.set_sensitive, True)
            GLib.idle_add(self.fetch_btn.set_label, "Fetch Formats")

    def parse_formats(self, output):
        lines = output.splitlines()
        all_formats = []
        in_format_section = False

        for line in lines:
            if "format code" in line.lower() or ("ID" in line and "EXT" in line):
                in_format_section = True
                continue
            if not in_format_section or not line.strip():
                continue
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            fmt_id = parts[0]
            if not re.match(r"^[0-9a-zA-Z_+/]+$", fmt_id):
                continue
            ext = parts[1]
            label = fmt_id + " - " + ext.upper() + "  " + " ".join(parts[2:])
            if not ("video only" in line.lower()):
                all_formats.append({'id': fmt_id, 'label': label})
        return all_formats

    def update_format_dropdown(self):
        self.v_format_combo.remove_all()
        if not self.all_formats:
            self.v_format_combo.append("none", "No formats found")
            self.v_format_combo.set_active_id("none")
            return
        
        # Filter formats based on mode
        formats_to_show = self.all_formats
        if not self.is_video_mode:
            # Audio mode: show only audio-friendly formats (m4a, mp3, opus, vorbis, etc.)
            audio_exts = {'m4a', 'mp3', 'opus', 'vorbis', 'wav', 'aac'}
            formats_to_show = [f for f in self.all_formats 
                              if f['label'].split('-')[1].strip().split()[0].lower() in audio_exts]
            
            if not formats_to_show:
                formats_to_show = self.all_formats
                self.log_status("[WARN] No audio-specific formats found, showing all formats")
            else:
                self.log_status(f"[FORMAT] Showing {len(formats_to_show)} audio-compatible formats")
        
        for fmt in formats_to_show:
            self.v_format_combo.append(fmt["id"], fmt["label"])
        self.v_format_combo.set_active(0)

    # ----- Download logic -----
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

        if not self.is_video_mode:
            cmd.append("--extract-audio")

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
        GLib.idle_add(self.log_status, "[CMD] " + " ".join(cmd))
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
        except Exception as e:
            GLib.idle_add(self.log_status, "[ERROR][DownloadThread] " + str(e))
        finally:
            self.process = None

    def show_error(self, msg):
        dlg = Gtk.MessageDialog(transient_for=self, flags=0,
                                message_type=Gtk.MessageType.ERROR,
                                buttons=Gtk.ButtonsType.OK, text=msg)
        dlg.run()
        dlg.destroy()
        self.log_status("[ERROR] " + msg)


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