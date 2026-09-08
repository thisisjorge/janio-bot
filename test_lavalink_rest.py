import urllib.parse
import urllib.request
import json

queries = [
    ("ytsearch:", "ytsearch:never gonna give you up"),
    ("URL normal", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("URL youtu.be", "https://youtu.be/dQw4w9WgXcQ"),
    ("YouTube Music", "https://music.youtube.com/watch?v=dQw4w9WgXcQ")
]

print("Iniciando testes no Lavalink REST API...")
for test_name, query in queries:
    url = f"http://127.0.0.1:2333/v4/loadtracks?identifier={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"Authorization": "youshallnotpass"})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            load_type = data.get("loadType")
            if load_type in ("track", "playlist", "search"):
                tracks = data.get("data")
                if load_type == "search" or load_type == "playlist":
                    # data is a list (for search) or object (for playlist)
                    tracks_list = tracks if isinstance(tracks, list) else tracks.get("tracks", [])
                    print(f"[SUCESSO] {test_name}: Encontrou {len(tracks_list)} faixas.")
                    if tracks_list:
                        track = tracks_list[0].get("info", {})
                        print(f"          Primeira faixa: {track.get('title')} ({track.get('uri')})")
                elif load_type == "track":
                    track = tracks.get("info", {})
                    print(f"[SUCESSO] {test_name}: Encontrou 1 faixa.")
                    print(f"          Faixa: {track.get('title')} ({track.get('uri')})")
            elif load_type == "empty":
                print(f"[FALHA] {test_name}: Nenhuma faixa encontrada.")
            elif load_type == "error":
                print(f"[ERRO] {test_name}: {data.get('data', {}).get('message')}")
    except Exception as e:
        print(f"[ERRO] {test_name}: {e}")
