from pytubefix import YouTube

try:
    yt = YouTube('https://youtu.be/nIPGdv-vkSY')
    print('Title:', yt.title)
    stream = yt.streams.get_audio_only()
    print('Stream URL:', stream.url)
except Exception as e:
    import traceback
    traceback.print_exc()
