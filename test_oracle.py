import yt_dlp

query = 'https://youtu.be/nIPGdv-vkSY'
options = {
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
    'proxy': 'socks5://127.0.0.1:40000',
    'extractor_args': {'youtube': {'player_client': ['web']}},
}
try:
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(query, download=False)
    print('SUCCESS')
    print('title:', info.get('title'))
except Exception as e:
    import traceback
    traceback.print_exc()
