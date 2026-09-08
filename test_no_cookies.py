import yt_dlp
from typing import Any, cast

def test_client(client_name: str):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "default_search": "ytsearch",
        "extractor_args": {"youtube": {"player_client": [client_name]}},
        # NOT setting cookiefile
    }
    print(f"Testing client NO COOKIES: {client_name}")
    try:
        with yt_dlp.YoutubeDL(cast(Any, options)) as downloader:
            info = downloader.extract_info("ytsearch:The Long Faces - Jane!", download=False)
            if info and "entries" in info and len(info["entries"]) > 0:
                print(f"SUCCESS with {client_name}: {info['entries'][0]['title']}")
            else:
                print(f"FAILED to extract with {client_name}")
    except Exception as e:
        print(f"ERROR with {client_name}: {e}")

if __name__ == "__main__":
    for client in ["android", "ios", "web_safari", "tv", "android_creator"]:
        test_client(client)
        print("-" * 40)
