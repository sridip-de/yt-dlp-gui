#!/usr/bin/env python3
import gi
import os
import threading
import subprocess
from pathlib import Path

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

class YtDlpGUI(Gtk.ApplicationWindow):
    QUALITY_OPTIONS = {
        "video": [("best", "Best Available"), ("1080", "1080p"), ("720", "720p"), 
                  ("480", "480p"), ("360", "360p")],
        "audio": [("best", "Best Available"), ("192", "192 kbps"), ("128", "128 kbps"), ("64", "64 kbps")]
    }
    
    FORMAT_OPTIONS = {
        "video": [("best", "Best (auto)"), ("mp4", "MP4"), ("mkv", "MKV"), ("webm", "WebM")],
        "audio": [("best", "Best (auto)"), ("mp3", "MP3"), ("m4a", "M4A"), ("wav", "WAV"), ("opus", "Opus")]
    }
    
    SUB_LANGS = [("en", "English"), ("all", "All Available"), ("es", "Spanish"), 
                 ("fr", "French"), ("de", "German"), ("hi", "Hindi")]
    
    def __init__(self, app):
        super().__init__(application=app, title="yt-dlp GUI Manager")
        self.set_default_size(700, 850)
        self.set_border_width(10)
        self.set_icon_name("application-x-executable")
        
        self.download_thread = None
        self.process = None
        self.setup_ui()
        
    def create_labeled_combo(self, label_text, options, active_id="best"):
        """Helper to create labeled comboboxes"""
        label = Gtk.Label(label=label_text, xalign=0)
        combo = Gtk.ComboBoxText()
        for opt_id, opt_label in options:
            combo.append(opt_id, opt_label)
        combo.set_active_id(active_id)
        return label, combo
    
    def create_frame(self, title, spacing=8):
        """Helper to create styled frames"""
        frame = Gtk.Frame(label=title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
        for margin in ['top', 'bottom', 'start', 'end']:
            getattr(box, f'set_margin_{margin}')(10)
        frame.add(box)
        return frame, box
    
    def setup_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add(main_box)
        
        # URL Input
        url_label = Gtk.Label(label="URL:", xalign=0)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_placeholder_text("Enter YouTube URL...")
        main_box.pack_start(url_label, False, False, 0)
        main_box.pack_start(self.url_entry, False, False, 0)
        
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
        
        v_quality_label, self.quality_combo = self.create_labeled_combo(
            "Quality:", self.QUALITY_OPTIONS["video"], "best")
        video_box.pack_start(v_quality_label, False, False, 0)
        video_box.pack_start(self.quality_combo, False, False, 0)
        
        v_format_label, self.v_format_combo = self.create_labeled_combo(
            "Video Format:", self.FORMAT_OPTIONS["video"], "best")
        video_box.pack_start(v_format_label, False, False, 0)
        video_box.pack_start(self.v_format_combo, False, False, 0)
        
        main_box.pack_start(self.video_frame, False, False, 0)
        
        # Audio Settings Frame
        audio_frame, audio_box = self.create_frame("Audio Settings")
        
        a_quality_label, self.a_quality_combo = self.create_labeled_combo(
            "Audio Quality:", self.QUALITY_OPTIONS["audio"], "best")
        audio_box.pack_start(a_quality_label, False, False, 0)
        audio_box.pack_start(self.a_quality_combo, False, False, 0)
        
        a_format_label, self.a_format_combo = self.create_labeled_combo(
            "Audio Format:", self.FORMAT_OPTIONS["audio"], "best")
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
            "Subtitle Language:", self.SUB_LANGS, "en")
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
        
        button_box.pack_start(download_btn, True, True, 0)
        button_box.pack_start(cancel_btn, True, True, 0)
        
        main_box.pack_end(button_box, False, False, 0)
        
        self.show_all()
        self.video_frame.hide()
        
    def on_type_changed(self, combo):
        is_video = combo.get_active_id() == "video"
        self.video_frame.set_visible(is_video)
        self.embed_sub_check.set_sensitive(is_video and self.subtitle_check.get_active())
    
    def on_subtitle_toggled(self, check):
        is_active = check.get_active()
        self.sub_lang_combo.set_sensitive(is_active)
        self.embed_sub_check.set_sensitive(is_active and self.type_combo.get_active_id() == "video")
    
    def on_browse_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Download Location",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                          Gtk.STOCK_OK, Gtk.ResponseType.OK)
        
        if dialog.run() == Gtk.ResponseType.OK:
            self.location_entry.set_text(dialog.get_filename())
        dialog.destroy()
    
    def log_status(self, message):
        text_buffer = self.status_view.get_buffer()
        text_buffer.insert(text_buffer.get_end_iter(), message + "\n")
        self.status_view.scroll_mark_onscreen(text_buffer.get_insert())
    
    def on_download_clicked(self, button):
        url = self.url_entry.get_text().strip()
        if not url:
            self.show_error("Please enter a URL")
            return
        
        self.download_thread = threading.Thread(target=self.start_download, args=(url,), daemon=True)
        self.download_thread.start()
    
    def on_cancel_clicked(self, button):
        if self.process:
            self.process.terminate()
            GLib.idle_add(self.log_status, "[CANCELLED] Download stopped by user")
    
    def build_cmd(self, url):
        """Build yt-dlp command based on settings"""
        cmd = ["yt-dlp"]
        
        # Add necessary options for reliability
        cmd.extend([
            "--no-warnings",
            "-R", "10",  # Retry 10 times
            "--socket-timeout", "30",
            "--extractor-args", "youtube:player_client=web,youtube:ignore_consent_challenge=true",
            "--http-header", "User-Agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "--no-check-certificates"
        ])
        
        if self.playlist_check.get_active():
            cmd.append("-i")
        
        download_type = self.type_combo.get_active_id()
        location = self.location_entry.get_text()
        
        if download_type == "audio":
            cmd.append("-x")
            audio_format = self.a_format_combo.get_active_id()
            if audio_format != "best":
                cmd.extend(["--audio-format", audio_format])
            audio_quality = self.a_quality_combo.get_active_id()
            if audio_quality != "best":
                cmd.extend(["--audio-quality", audio_quality])
            if self.thumbnail_check.get_active():
                cmd.append("--embed-thumbnail")
        else:
            quality = self.quality_combo.get_active_id()
            if quality == "best":
                cmd.extend(["-f", "bv*+ba/b"])
            else:
                cmd.extend(["-f", f"bv*[height<={quality}]+ba/b"])
            
            v_format = self.v_format_combo.get_active_id()
            if v_format != "best":
                cmd.extend(["--merge-output-format", v_format])
        
        if self.subtitle_check.get_active():
            cmd.append("--write-subs")
            sub_lang = self.sub_lang_combo.get_active_id()
            cmd.extend(["--sub-langs", sub_lang])
            if self.embed_sub_check.get_active() and download_type == "video":
                cmd.append("--embed-subs")
        
        cmd.extend(["-o", f"{location}/%(title)s.%(ext)s", url])
        return cmd
    
    def start_download(self, url):
        GLib.idle_add(self.log_status, f"Starting download from: {url}")
        GLib.idle_add(self.progress_bar.set_fraction, 0)
        
        try:
            cmd = self.build_cmd(url)
            GLib.idle_add(self.log_status, f"Command: {' '.join(cmd)}")
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, bufsize=1
            )
            
            has_error = False
            for line in self.process.stdout:
                line = line.rstrip()
                GLib.idle_add(self.log_status, line)
                
                if line.startswith("ERROR"):
                    has_error = True
                
                if "%" in line and "ETA" in line:
                    try:
                        percent = float(line.split("%")[0].split()[-1])
                        GLib.idle_add(self.progress_bar.set_fraction, min(percent / 100, 1.0))
                    except (ValueError, IndexError):
                        pass
            
            self.process.wait()
            if self.process.returncode == 0 and not has_error:
                GLib.idle_add(self.log_status, "[SUCCESS] Download completed!")
                GLib.idle_add(self.progress_bar.set_fraction, 1.0)
            else:
                GLib.idle_add(self.log_status, "[FAILED] Download encountered errors. Check output above.")
                GLib.idle_add(self.progress_bar.set_fraction, 0)
            
        except FileNotFoundError:
            GLib.idle_add(self.show_error, "yt-dlp not found. Install: pip install yt-dlp")
        except Exception as e:
            GLib.idle_add(self.show_error, f"Error: {str(e)}")
        finally:
            self.process = None
    
    def show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=message
        )
        dialog.run()
        dialog.destroy()
        self.log_status(f"[ERROR] {message}")

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
    app.run(None)