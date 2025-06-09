import sys
import os
import yt_dlp
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply


class DownloadThread(QtCore.QThread):
    progress_signal = QtCore.pyqtSignal(int)
    status_signal = QtCore.pyqtSignal(str)
    finished_signal = QtCore.pyqtSignal(str)  # Emit the output path on finish

    def __init__(self, url, path, parent=None):
        super().__init__(parent)
        self.url = url
        self.path = path
        self.thumbnail_path = None

    def run(self):
        def hook(d):
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
                    unit = 'bytes/s'
                    if speed > 1024 * 1024:
                        speed /= (1024 * 1024)
                        unit = 'MB/s'
                    elif speed > 1024:
                        speed /= 1024
                        unit = 'KB/s'
                    status_text += f" {speed:.2f} {unit}"
                self.status_signal.emit(status_text)

            elif d['status'] == 'finished':
                self.progress_signal.emit(100)
                self.status_signal.emit("✅ Download finished!")
                if 'tmpfilename' in d and 'filename' in d and os.path.exists(d['filename']):
                    self.finished_signal.emit(d['filename']) # Emit the final file path

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(self.path, '%(title)s.%(ext)s'),
            'progress_hooks': [hook],
            'merge_output_format': 'mp4',
            'writethumbnail': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                if info and 'thumbnail' in info:
                    self.thumbnail_path = ydl.prepare_filename(info) + ".jpg" # Construct thumbnail path
                ydl.download([self.url])
        except Exception as e:
            self.status_signal.emit(f"❌ Error: {str(e)}")

        if self.thumbnail_path and os.path.exists(self.thumbnail_path):
            try:
                os.remove(self.thumbnail_path)
                print(f"Deleted thumbnail: {self.thumbnail_path}")
            except Exception as e:
                print(f"Error deleting thumbnail {self.thumbnail_path}: {e}")


class VideoDownloaderApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ Phinix Downloader")
        self.setGeometry(100, 100, 700, 450)
        self.setStyleSheet("background-color: #1e1e1e; color: white; font-size: 14px;")
        self.selected_path = ""
        self.download_thread = None
        self.thumbnail_label = QtWidgets.QLabel(self)
        self.thumbnail_pixmap = None
        self.network_manager = QNetworkAccessManager()
        self.thumbnail_timer = QTimer(self) # Create a QTimer instance
        self.current_url = ""
        self.init_ui()

    def init_ui(self):
        # Top Layout
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(QtWidgets.QLabel("Paste Video URL:", self))
        self.url_input = QtWidgets.QLineEdit(self)
        self.url_input.setStyleSheet("background-color: #2c2c2c; border: 1px solid #444; border-radius: 6px; padding: 5px;")
        self.url_input.textChanged.connect(self.delayed_fetch_thumbnail) # Connect to the delayed function
        top_layout.addWidget(self.url_input)
        self.path_button = QtWidgets.QPushButton("Select Download Folder", self)
        self.path_button.clicked.connect(self.select_path)
        self.path_button.setStyleSheet(self.button_style())
        top_layout.addWidget(self.path_button)

        # Thumbnail Preview
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet("border: 2px solid #555; border-radius: 8px; background-color: #2c2c2c;")
        self.thumbnail_label.setFixedSize(400, 225)

        # Bottom Layout
        bottom_layout = QtWidgets.QVBoxLayout()
        self.download_button = QtWidgets.QPushButton("Download", self)
        self.download_button.clicked.connect(self.download_video)
        self.download_button.setStyleSheet(self.button_style())
        bottom_layout.addWidget(self.download_button)
        self.status_label = QtWidgets.QLabel("Status: Ready", self)
        bottom_layout.addWidget(self.status_label)

        # Main Layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.thumbnail_label)
        main_layout.addLayout(bottom_layout)

        # Timer setup
        self.thumbnail_timer.timeout.connect(self._fetch_thumbnail)
        self.thumbnail_timer.setSingleShot(True) # Only trigger once

    def button_style(self):
        return """
            QPushButton {
                background-color: #3c3f41;
                color: white;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #00ff88;
                color: black;
            }
        """

    def select_path(self):
        self.selected_path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if self.selected_path:
            self.status_label.setText(f"Selected Path: {self.selected_path}")

    def delayed_fetch_thumbnail(self, url):
        if url != self.current_url:
            self.current_url = url
            self.thumbnail_timer.start(500) # Wait for 500 milliseconds (adjust as needed)

    def _fetch_thumbnail(self):
        url = self.current_url
        if url:
            self.status_label.setText("🔍 Fetching thumbnail...")
            ydl_opts_thumb = {
                'writethumbnail': True,
                'skip_download': True,
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts_thumb) as ydl_thumb:
                    info = ydl_thumb.extract_info(url, download=False)
                    if info and 'thumbnail' in info:
                        thumbnail_url = info['thumbnail']
                        self.download_thumbnail(thumbnail_url)
                    else:
                        self.thumbnail_label.setText("🚫 No Thumbnail Found")
                        self.thumbnail_label.setStyleSheet("border: 2px solid #555; border-radius: 8px; background-color: #444; color: white;")
                        self.status_label.setText("⚠️ Could not fetch thumbnail.")
            except Exception as e:
                self.thumbnail_label.setText("🚫 Error Fetching Thumbnail")
                self.thumbnail_label.setStyleSheet("border: 2px solid #555; border-radius: 8px; background-color: #444; color: white;")
                self.status_label.setText(f"❌ Thumbnail info error: {str(e)}")
        else:
            self.thumbnail_label.clear()
            self.thumbnail_label.setStyleSheet("border: 2px solid #555; border-radius: 8px; background-color: #2c2c2c;")
            self.status_label.setText("Status: Ready")


    def download_thumbnail(self, url):
        request = QNetworkRequest(QtCore.QUrl(url))
        self.reply = self.network_manager.get(request)
        self.reply.finished.connect(self.slot_downloaded)

    def slot_downloaded(self):
        if self.reply.error() == QNetworkReply.NoError:
            data = self.reply.readAll()
            image = QtGui.QImage.fromData(data)
            if not image.isNull():
                scaled_image = image.scaled(400, 225, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.thumbnail_pixmap = QtGui.QPixmap.fromImage(scaled_image)
                self.thumbnail_label.setPixmap(self.thumbnail_pixmap)
            else:
                self.thumbnail_label.setText("🚫 Invalid Thumbnail")
                self.thumbnail_label.setStyleSheet("border: 2px solid #555; border-radius: 8px; background-color: #444; color: white;")
        else:
            self.thumbnail_label.setText(f"🚫 Error Loading Thumbnail: {self.reply.errorString()}")
            self.thumbnail_label.setStyleSheet("border: 2px solid #555; border-radius: 8px; background-color: #444; color: white;")
            print(f"Thumbnail Download Error: {self.reply.errorString()}")

        self.reply.deleteLater()


    def download_video(self):
        url = self.url_input.text()
        if not url or not self.selected_path:
            self.status_label.setText("❌ Please provide a valid URL and select a path.")
            return

        self.status_label.setText("🚀 Download started...")
        self.download_button.setEnabled(False)

        self.download_thread = DownloadThread(url, self.selected_path, self)
        self.download_thread.progress_signal.connect(lambda x: None) # Disconnect progress bar
        self.download_thread.status_signal.connect(self.status_label.setText)
        self.download_thread.finished_signal.connect(self.slot_download_finished)
        self.download_thread.start()


    def slot_download_finished(self, output_path):
        self.download_button.setEnabled(True)
        self.status_label.setText(f"✅ Done! Video saved to: {output_path}")

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = VideoDownloaderApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()