import asyncio
import os
import wavelink
from dotenv import load_dotenv

load_dotenv()

class DummyBot:
    def __init__(self):
        self.loop = asyncio.get_event_loop()

async def main():
    bot = DummyBot()
    
    nodes = [wavelink.Node(uri="http://127.0.0.1:2333", password="youshallnotpass")]
    await wavelink.Pool.connect(nodes=nodes, client=bot, cache_capacity=100)
    
    queries = [
        ("ytsearch:", "ytsearch:never gonna give you up"),
        ("URL normal", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
        ("URL youtu.be", "https://youtu.be/dQw4w9WgXcQ"),
        ("YouTube Music", "https://music.youtube.com/watch?v=dQw4w9WgXcQ")
    ]
    
    print("Iniciando testes no Lavalink...")
    for test_name, query in queries:
        try:
            print(f"\n--- Testando {test_name} ---")
            tracks = await wavelink.Playable.search(query)
            if tracks:
                print(f"[SUCESSO] {test_name}: Encontrou {len(tracks) if isinstance(tracks, wavelink.Playlist) else 1} faixas.")
                track = tracks.tracks[0] if isinstance(tracks, wavelink.Playlist) else tracks[0]
                print(f"          Primeira faixa: {track.title} ({track.uri})")
            else:
                print(f"[FALHA] {test_name}: Nenhuma faixa encontrada.")
        except Exception as e:
            print(f"[ERRO] {test_name}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
