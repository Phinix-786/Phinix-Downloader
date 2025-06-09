import yt_dlp

def download_video(url, download_path):
    ydl_opts = {
        'outtmpl': f'{download_path}/%(title)s.%(ext)s',  # Output path template
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
