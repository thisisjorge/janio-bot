import yt_dlp
options = {"format": "bestaudio/best", "cookiefile": "cookies.txt", "noplaylist": True, "default_search": "ytsearch"}
try:
    yt_dlp.YoutubeDL(options).extract_info("ytsearch1:parangole balacubaco", download=False)
except Exception as e:
    print("ERROR:", e)
