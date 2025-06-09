import sys
import os
import yt_dlp
import json
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import (QFileDialog, QProgressBar, QComboBox, 
                             QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QTextEdit, QCheckBox, QGroupBox,
                             QMessageBox, QSplitter)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class DownloadThread(QThread):
    progress_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)

    def __init__(self, url, path, format_choice='best', audio_only=False, parent=None):
        super().__init__(parent)
        self.url = url
        self.path = path
        self.format_choice = format_choice
        self.audio_only = audio_only
        self.is_cancelled = False

    def run(self):
        def hook(d):
            if self.is_cancelled:
                return
                
            if d['status'] == 'downloading':
                percent = 0
                if 'total_bytes' in d and d['total_bytes']:
                    downloaded_bytes = d.get('downloaded_bytes', 0)
                    total_bytes = d['total_bytes']
                    if total_bytes > 0:
                        percent = int((downloaded_bytes / total_bytes) * 100)
                elif '_percent_str' in d:
                    percent_str = d['_percent_str'].strip().replace('%', '')
                    try:
                        percent = int(float(percent_str))
                    except ValueError:
                        percent = 0

                self.progress_signal.emit(percent)

                status_text = "🚀 Downloading..."
                if 'speed' in d and d['speed'] is not None:
                    speed = d['speed']
                    unit = 'B/s'
                    if speed > 1024 * 1024:
                        speed /= (1024 * 1024)
                        unit = 'MB/s'
                    elif speed > 1024:
                        speed /= 1024
                        unit = 'KB/s'
                    status_text += f" Speed: {speed:.2f} {unit}"
                
                if 'eta' in d and d['eta'] is not None:
                    eta = d['eta']
                    minutes, seconds = divmod(eta, 60)
                    status_text += f" | ETA: {int(minutes):02d}:{int(seconds):02d}"
                
                self.status_signal.emit(status_text)
                self.log_signal.emit(f"Progress: {percent}% - {status_text}")

            elif d['status'] == 'finished':
                self.progress_signal.emit(100)
                self.status_signal.emit("✅ Download completed!")
                if 'filename' in d and os.path.exists(d['filename']):
                    self.finished_signal.emit(d['filename'])
                    self.log_signal.emit(f"✅ Download completed: {d['filename']}")

        # Set up download options
        if self.audio_only:
            format_selector = 'bestaudio/best'
            output_ext = 'mp3'
        else:
            format_map = {
                'Best Quality': 'bestvideo+bestaudio/best',
                '1080p': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                '720p': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                '480p': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
                '360p': 'bestvideo[height<=360]+bestaudio/best[height<=360]'
            }
            format_selector = format_map.get(self.format_choice, 'best')
            output_ext = 'mp4'

        ydl_opts = {
            'format': format_selector,
            'outtmpl': os.path.join(self.path, '%(title)s.%(ext)s'),
            'progress_hooks': [hook],
            'merge_output_format': output_ext,
            'writeinfojson': False,
            'writethumbnail': False,
            'ignoreerrors': False,
        }

        # Add audio extraction options if audio only
        if self.audio_only:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        try:
            self.log_signal.emit(f"Starting download from: {self.url}")
            self.log_signal.emit(f"Format: {format_selector}")
            self.log_signal.emit(f"Output path: {self.path}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = f"Download Error: {str(e)}"
            self.error_signal.emit(error_msg)
            self.log_signal.emit(f"❌ {error_msg}")
        except Exception as e:
            error_msg = f"Unexpected Error: {str(e)}"
            self.error_signal.emit(error_msg)
            self.log_signal.emit(f"❌ {error_msg}")

    def cancel(self):
        self.is_cancelled = True
        self.terminate()


class VideoInfoThread(QThread):
    info_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.info_signal.emit(info)
        except Exception as e:
            self.error_signal.emit(str(e))


class VideoDownloaderApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ Advanced Video Downloader")
        self.setGeometry(100, 100, 1000, 700)
        self.setStyleSheet(self.get_app_stylesheet())
        
        # Initialize variables
        self.selected_path = os.path.expanduser("~/Downloads")
        self.download_thread = None
        self.info_thread = None
        self.thumbnail_label = QLabel(self)
        self.network_manager = QNetworkAccessManager()
        self.thumbnail_timer = QTimer(self)
        self.current_url = ""
        self.video_info = {}
        
        self.init_ui()
        self.setup_connections()

    def get_app_stylesheet(self):
        return """
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px;
            }
            QLineEdit {
                background-color: #2d2d2d;
                border: 2px solid #404040;
                border-radius: 8px;
                padding: 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #00ff88;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #00ff88;
                color: #000000;
            }
            QPushButton:pressed {
                background-color: #00cc6a;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QComboBox {
                background-color: #2d2d2d;
                border: 2px solid #404040;
                border-radius: 8px;
                padding: 8px;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #00ff88;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-style: solid;
                border-width: 3px;
                border-color: #ffffff transparent transparent transparent;
            }
            QProgressBar {
                border: 2px solid #404040;
                border-radius: 8px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #00ff88, stop:1 #00cc6a);
                border-radius: 6px;
            }
            QTextEdit {
                background-color: #2d2d2d;
                border: 2px solid #404040;
                border-radius: 8px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #404040;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #404040;
                border-radius: 4px;
                background-color: #2d2d2d;
            }
            QCheckBox::indicator:checked {
                background-color: #00ff88;
                border-color: #00ff88;
            }
            QLabel {
                color: #ffffff;
            }
        """

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Create splitter for resizable layout
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel
        left_panel = self.create_left_panel()
        splitter.addWidget(left_panel)
        
        # Right panel (log)
        right_panel = self.create_right_panel()
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([700, 300])
        
        main_layout.addWidget(splitter)

    def create_left_panel(self):
        left_widget = QtWidgets.QWidget()
        layout = QVBoxLayout(left_widget)
        
        # URL Input Section
        url_group = QGroupBox("Video URL")
        url_layout = QVBoxLayout(url_group)
        
        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste YouTube, Vimeo, or other video URL here...")
        url_input_layout.addWidget(self.url_input)
        
        self.fetch_info_btn = QPushButton("Fetch Info")
        self.fetch_info_btn.setFixedWidth(100)
        url_input_layout.addWidget(self.fetch_info_btn)
        
        url_layout.addLayout(url_input_layout)
        layout.addWidget(url_group)
        
        # Video Info Section
        info_group = QGroupBox("Video Information")
        info_layout = QHBoxLayout(info_group)
        
        # Thumbnail
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("""
            border: 2px solid #555;
            border-radius: 8px;
            background-color: #2c2c2c;
            color: #888;
        """)
        self.thumbnail_label.setFixedSize(300, 170)
        self.thumbnail_label.setText("No thumbnail loaded")
        info_layout.addWidget(self.thumbnail_label)
        
        # Video details
        details_layout = QVBoxLayout()
        self.title_label = QLabel("Title: Not loaded")
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        
        self.duration_label = QLabel("Duration: Unknown")
        self.uploader_label = QLabel("Uploader: Unknown")
        self.views_label = QLabel("Views: Unknown")
        
        details_layout.addWidget(self.title_label)
        details_layout.addWidget(self.duration_label)
        details_layout.addWidget(self.uploader_label)
        details_layout.addWidget(self.views_label)
        details_layout.addStretch()
        
        info_layout.addLayout(details_layout)
        layout.addWidget(info_group)
        
        # Download Settings Section
        settings_group = QGroupBox("Download Settings")
        settings_layout = QVBoxLayout(settings_group)
        
        # Path selection
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("Download Path:"))
        self.path_label = QLabel(self.selected_path)
        self.path_label.setStyleSheet("color: #00ff88; font-weight: bold;")
        path_layout.addWidget(self.path_label)
        path_layout.addStretch()
        
        self.path_button = QPushButton("Browse")
        self.path_button.setFixedWidth(80)
        path_layout.addWidget(self.path_button)
        settings_layout.addLayout(path_layout)
        
        # Format selection
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("Video Quality:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(['Best Quality', '1080p', '720p', '480p', '360p'])
        format_layout.addWidget(self.format_combo)
        
        self.audio_only_checkbox = QCheckBox("Audio Only (MP3)")
        format_layout.addWidget(self.audio_only_checkbox)
        format_layout.addStretch()
        
        settings_layout.addLayout(format_layout)
        layout.addWidget(settings_group)
        
        # Progress Section
        progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet("font-weight: bold; color: #00ff88;")
        progress_layout.addWidget(self.status_label)
        
        # Download buttons
        button_layout = QHBoxLayout()
        self.download_button = QPushButton("🚀 Start Download")
        self.download_button.setStyleSheet("font-size: 14px; padding: 12px;")
        self.cancel_button = QPushButton("❌ Cancel")
        self.cancel_button.setVisible(False)
        
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.cancel_button)
        progress_layout.addLayout(button_layout)
        
        layout.addWidget(progress_group)
        
        return left_widget

    def create_right_panel(self):
        right_widget = QtWidgets.QWidget()
        layout = QVBoxLayout(right_widget)
        
        log_group = QGroupBox("Download Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.append("📋 Download log will appear here...")
        
        clear_log_btn = QPushButton("Clear Log")
        clear_log_btn.setFixedHeight(30)
        clear_log_btn.clicked.connect(self.log_text.clear)
        
        log_layout.addWidget(self.log_text)
        log_layout.addWidget(clear_log_btn)
        
        layout.addWidget(log_group)
        
        return right_widget

    def setup_connections(self):
        self.url_input.textChanged.connect(self.on_url_changed)
        self.fetch_info_btn.clicked.connect(self.fetch_video_info)
        self.path_button.clicked.connect(self.select_path)
        self.download_button.clicked.connect(self.start_download)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.audio_only_checkbox.toggled.connect(self.on_audio_only_toggled)
        
        # Timer for delayed info fetching
        self.thumbnail_timer.timeout.connect(self.fetch_video_info)
        self.thumbnail_timer.setSingleShot(True)

    def on_url_changed(self, url):
        if url != self.current_url:
            self.current_url = url
            self.reset_video_info()
            if url.strip():
                self.thumbnail_timer.start(1000)  # Delay 1 second

    def on_audio_only_toggled(self, checked):
        self.format_combo.setEnabled(not checked)

    def reset_video_info(self):
        self.thumbnail_label.clear()
        self.thumbnail_label.setText("No thumbnail loaded")
        self.title_label.setText("Title: Not loaded")
        self.duration_label.setText("Duration: Unknown")
        self.uploader_label.setText("Uploader: Unknown")
        self.views_label.setText("Views: Unknown")
        self.video_info = {}

    def fetch_video_info(self):
        url = self.url_input.text().strip()
        if not url:
            return
            
        self.status_label.setText("🔍 Fetching video information...")
        self.fetch_info_btn.setEnabled(False)
        
        self.info_thread = VideoInfoThread(url)
        self.info_thread.info_signal.connect(self.on_info_received)
        self.info_thread.error_signal.connect(self.on_info_error)
        self.info_thread.start()

    def on_info_received(self, info):
        self.video_info = info
        self.fetch_info_btn.setEnabled(True)
        
        # Update video information
        title = info.get('title', 'Unknown Title')
        duration = info.get('duration', 0)
        uploader = info.get('uploader', 'Unknown')
        view_count = info.get('view_count', 0)
        
        self.title_label.setText(f"Title: {title}")
        
        if duration:
            minutes, seconds = divmod(duration, 60)
            hours, minutes = divmod(minutes, 60)
            if hours:
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes:02d}:{seconds:02d}"
            self.duration_label.setText(f"Duration: {duration_str}")
        
        self.uploader_label.setText(f"Uploader: {uploader}")
        
        if view_count:
            if view_count >= 1000000:
                views_str = f"{view_count/1000000:.1f}M"
            elif view_count >= 1000:
                views_str = f"{view_count/1000:.1f}K"
            else:
                views_str = str(view_count)
            self.views_label.setText(f"Views: {views_str}")
        
        # Load thumbnail
        thumbnail_url = info.get('thumbnail')
        if thumbnail_url:
            self.download_thumbnail(thumbnail_url)
        
        self.status_label.setText("✅ Video information loaded successfully!")
        self.log_text.append(f"📹 Video: {title}")
        self.log_text.append(f"👤 Uploader: {uploader}")

    def on_info_error(self, error):
        self.fetch_info_btn.setEnabled(True)
        self.status_label.setText(f"❌ Error fetching video info: {error}")
        self.log_text.append(f"❌ Info fetch error: {error}")

    def download_thumbnail(self, url):
        request = QNetworkRequest(QtCore.QUrl(url))
        reply = self.network_manager.get(request)
        reply.finished.connect(lambda: self.on_thumbnail_downloaded(reply))

    def on_thumbnail_downloaded(self, reply):
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            image = QtGui.QImage.fromData(data)
            if not image.isNull():
                scaled_image = image.scaled(300, 170, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                pixmap = QtGui.QPixmap.fromImage(scaled_image)
                self.thumbnail_label.setPixmap(pixmap)
            else:
                self.thumbnail_label.setText("🚫 Invalid thumbnail")
        else:
            self.thumbnail_label.setText("🚫 Thumbnail load failed")
        
        reply.deleteLater()

    def select_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Download Directory", self.selected_path)
        if path:
            self.selected_path = path
            self.path_label.setText(path)
            self.log_text.append(f"📁 Download path set to: {path}")

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a valid URL!")
            return
        
        if not self.selected_path or not os.path.exists(self.selected_path):
            QMessageBox.warning(self, "Warning", "Please select a valid download directory!")
            return
        
        # UI changes for download state
        self.download_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("🚀 Preparing download...")
        
        # Get settings
        format_choice = self.format_combo.currentText()
        audio_only = self.audio_only_checkbox.isChecked()
        
        # Start download thread
        self.download_thread = DownloadThread(url, self.selected_path, format_choice, audio_only)
        self.download_thread.progress_signal.connect(self.progress_bar.setValue)
        self.download_thread.status_signal.connect(self.status_label.setText)
        self.download_thread.finished_signal.connect(self.on_download_finished)
        self.download_thread.error_signal.connect(self.on_download_error)
        self.download_thread.log_signal.connect(self.log_text.append)
        self.download_thread.start()

    def cancel_download(self):
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.status_label.setText("❌ Download cancelled")
            self.log_text.append("❌ Download cancelled by user")
        
        self.reset_download_ui()

    def on_download_finished(self, output_path):
        self.status_label.setText(f"✅ Download completed! File saved to: {os.path.basename(output_path)}")
        self.log_text.append(f"✅ Download completed successfully!")
        self.log_text.append(f"📁 File location: {output_path}")
        
        # Show completion message
        QMessageBox.information(self, "Download Complete", 
                              f"Video downloaded successfully!\n\nLocation: {output_path}")
        
        self.reset_download_ui()

    def on_download_error(self, error):
        self.status_label.setText(f"❌ Download failed: {error}")
        QMessageBox.critical(self, "Download Error", f"Download failed:\n\n{error}")
        self.reset_download_ui()

    def reset_download_ui(self):
        self.download_button.setVisible(True)
        self.cancel_button.setVisible(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')  # Use Fusion style for better appearance
    
    # Set application icon (if you have one)
    # app.setWindowIcon(QtGui.QIcon('icon.png'))
    
    window = VideoDownloaderApp()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
