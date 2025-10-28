#!/usr/bin/env python3
import gi
import os
import threading
import subprocess
import json
from pathlib import Path

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gdk

class YtDlpGUI(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="yt-dlp GUI Manager")
        self.set_default_size(700, 800)
        self.set_border_width(10)
        self.set_icon_name("application-x-executable")
        
        self.download_thread = None
        self.process = None
        
        self.setup_ui()
        
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
        
        # Video Quality Section
        self.video_frame = Gtk.Frame(label="Video Settings")
        video_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        video_box.set_margin_top(10)
        video_box.set_margin_bottom(10)
        video_box.set_margin_start(10)
        video_box.set_margin_end(10)
        
        quality_label = Gtk.Label(label="Quality:", xalign=0)
        self.quality_combo = Gtk.ComboBoxText()
        self.quality_combo.append("best", "Best Available")
        self.quality_combo.append("1080", "1080p")
        self.quality_combo.append("720", "720p")
        self.quality_combo.append("480", "480p")
        self.quality_combo.append("360", "360p")
        self.quality_combo.set_active_id("best")
        video_box.pack_start(quality_label, False, False, 0)
        video_box.pack_start(self.quality_combo, False, False, 0)
        
        v_format_label = Gtk.Label(label="Video Format:", xalign=0)
        self.v_format_combo = Gtk.ComboBoxText()
        self.v_format_combo.append("best", "Best (auto)")
        self.v_format_combo.append("mp4", "MP4")
        self.v_format_combo.append("mkv", "MKV")
        self.v_format_combo.append("webm", "WebM")
        self.v_format_combo.set_active_id("best")
        video_box.pack_start(v_format_label, False, False, 0)
        video_box.pack_start(self.v_format_combo, False, False, 0)
        
        self.video_frame.add(video_box)
        main_box.pack_start(self.video_frame, False, False, 0)
        
        # Audio Quality & Format Section
        audio_frame = Gtk.Frame(label="Audio Settings")
        audio_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        audio_box.set_margin_top(10)
        audio_box.set_margin_bottom(10)
        audio_box.set_margin_start(10)
        audio_box.set_margin_end(10)
        
        a_quality_label = Gtk.Label(label="Audio Quality:", xalign=0)
        self.a_quality_combo = Gtk.ComboBoxText()
        self.a_quality_combo.append("best", "Best Available")
        self.a_quality_combo.append("192", "192 kbps")
        self.a_quality_combo.append("128", "128 kbps")
        self.a_quality_combo.append("64", "64 kbps")
        self.a_quality_combo.set_active_id("best")
        audio_box.pack_start(a_quality_label, False, False, 0)
        audio_box.pack_start(self.a_quality_combo, False, False, 0)
        
        a_format_label = Gtk.Label(label="Audio Format:", xalign=0)
        self.a_format_combo = Gtk.ComboBoxText()
        self.a_format_combo.append("best", "Best (auto)")
        self.a_format_combo.append("mp3", "MP3")
        self.a_format_combo.append("m4a", "M4A")
        self.a_format_combo.append("wav", "WAV")
        self.a_format_combo.append("opus", "Opus")
        self.a_format_combo.set_active_id("best")
        audio_box.pack_start(a_format_label, False, False, 0)
        audio_box.pack_start(self.a_format_combo, False, False, 0)
        
        self.thumbnail_check = Gtk.CheckButton(label="Embed Thumbnail in Audio")
        self.thumbnail_check.set_active(False)
        audio_box.pack_start(self.thumbnail_check, False, False, 0)
        
        audio_frame.add(audio_box)
        main_box.pack_start(audio_frame, False, False, 0)
        
        # Subtitle Settings
        sub_frame = Gtk.Frame(label="Subtitle Settings")
        sub_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        sub_box.set_margin_top(10)
        sub_box.set_margin_bottom(10)
        sub_box.set_margin_start(10)
        sub_box.set_margin_end(10)
        
        self.subtitle_check = Gtk.CheckButton(label="Download Subtitles")
        self.subtitle_check.set_active(False)
        self.subtitle_check.connect("toggled", self.on_subtitle_toggled)
        sub_box.pack_start(self.subtitle_check, False, False, 0)
        
        self.embed_sub_check = Gtk.CheckButton(label="Embed Subtitles in Video")
        self.embed_sub_check.set_active(False)
        self.embed_sub_check.set_sensitive(False)
        sub_box.pack_start(self.embed_sub_check, False, False, 0)
        
        sub_lang_label = Gtk.Label(label="Subtitle Language:", xalign=0)
        self.sub_lang_combo = Gtk.ComboBoxText()
        self.sub_lang_combo.append("en", "English")
        self.sub_lang_combo.append("all", "All Available")
        self.sub_lang_combo.append("es", "Spanish")
        self.sub_lang_combo.append("fr", "French")
        self.sub_lang_combo.append("de", "German")
        self.sub_lang_combo.append("hi", "Hindi")
        self.sub_lang_combo.set_active_id("en")
        self.sub_lang_combo.set_sensitive(False)
        sub_box.pack_start(sub_lang_label, False, False, 0)
        sub_box.pack_start(self.sub_lang_combo, False, False, 0)
        
        sub_frame.add(sub_box)
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
        download_type = combo.get_active_id()
        if download_type == "video":
            self.video_frame.show_all()
            self.embed_sub_check.set_sensitive(True)
        else:
            self.video_frame.hide()
            self.embed_sub_check.set_sensitive(False)
    
    def on_subtitle_toggled(self, check):
        is_active = check.get_active()
        self.sub_lang_combo.set_sensitive(is_active)
        if self.type_combo.get_active_id() == "video":
            self.embed_sub_check.set_sensitive(is_active)
    
    def on_browse_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Download Location",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
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
        
        self.download_thread = threading.Thread(target=self.start_download, args=(url,))
        self.download_thread.daemon = True
        self.download_thread.start()
    
    def on_cancel_clicked(self, button):
        if self.process:
            self.process.terminate()
            GLib.idle_add(self.log_status, "[CANCELLED] Download stopped by user")
    
    def start_download(self, url):
        GLib.idle_add(self.log_status, f"Starting download from: {url}")
        GLib.idle_add(self.progress_bar.set_fraction, 0)
        
        download_type = self.type_combo.get_active_id()
        is_playlist = self.playlist_check.get_active()
        location = self.location_entry.get_text()
        
        cmd = ["yt-dlp"]
        
        if is_playlist:
            cmd.append("-i")
        
        if download_type == "audio":
            cmd.extend(["-x", "--audio-format", self.a_format_combo.get_active_id()])
            quality = self.a_quality_combo.get_active_id()
            if quality != "best":
                cmd.extend(["-S", f"aext:m4a/mp3/best"])
            else:
                cmd.append("-S")
                cmd.append("aext:m4a/mp3/best")
            
            if self.thumbnail_check.get_active():
                cmd.append("--embed-thumbnail")
        else:
            quality = self.quality_combo.get_active_id()
            v_format = self.v_format_combo.get_active_id()
            
            if quality == "best":
                cmd.append("-f")
                cmd.append("bestvideo+bestaudio/best")
            else:
                cmd.append("-f")
                cmd.append(f"best[height<={quality}]+bestaudio/best")
            
            if v_format != "best":
                cmd.extend(["--merge-output-format", v_format])
        
        if self.subtitle_check.get_active():
            sub_lang = self.sub_lang_combo.get_active_id()
            cmd.extend(["--write-subs", "--sub-langs", sub_lang])
            
            if self.embed_sub_check.get_active() and download_type == "video":
                cmd.append("--embed-subs")
        
        cmd.extend(["-o", f"{location}/%(title)s.%(ext)s", url])
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            for line in self.process.stdout:
                line = line.rstrip()
                GLib.idle_add(self.log_status, line)
                
                if "%" in line and "ETA" in line:
                    try:
                        percent = float(line.split("%")[0].split()[-1])
                        GLib.idle_add(self.progress_bar.set_fraction, percent / 100)
                    except:
                        pass
            
            self.process.wait()
            GLib.idle_add(self.log_status, "[SUCCESS] Download completed!")
            GLib.idle_add(self.progress_bar.set_fraction, 1.0)
            
        except FileNotFoundError:
            GLib.idle_add(self.show_error, "yt-dlp not found. Please install it: pip install yt-dlp")
        except Exception as e:
            GLib.idle_add(self.show_error, f"Error: {str(e)}")
        finally:
            self.process = None
    
    def show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
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