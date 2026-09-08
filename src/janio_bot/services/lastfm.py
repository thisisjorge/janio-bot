import asyncio
import os
from typing import Any

import pylast

class LastfmService:
    def __init__(self) -> None:
        self.api_key = os.environ.get("LASTFM_API_KEY")
        self.api_secret = os.environ.get("LASTFM_API_SECRET")
        self.network: pylast.LastFMNetwork | None = None
        
        if self.api_key and self.api_secret:
            try:
                self.network = pylast.LastFMNetwork(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                )
            except Exception as e:
                print(f"Erro ao inicializar API do Last.fm: {e}")

    async def generate_session_key(self, username: str, password: str) -> str:
        if not self.network:
            raise Exception("API do Last.fm não está configurada.")
        
        def _gen():
            password_hash = pylast.md5(password)
            sg = pylast.SessionKeyGenerator(self.network)
            return sg.get_session_key(username, password_hash)
        
        return await asyncio.to_thread(_gen)

    def _parse_track(self, full_title: str) -> tuple[str, str]:
        """Tenta extrair artista e música do título (ex: 'Artista - Música')."""
        if " - " in full_title:
            parts = full_title.split(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        return "Janio Bot", full_title.strip()

    def _get_user_network(self, session_key: str) -> pylast.LastFMNetwork | None:
        if not self.api_key or not self.api_secret:
            return None
        return pylast.LastFMNetwork(
            api_key=self.api_key,
            api_secret=self.api_secret,
            session_key=session_key,
        )

    async def update_now_playing(self, full_title: str, session_keys: list[str], explicit_artist: str | None = None) -> None:
        if not session_keys:
            return
        
        if explicit_artist:
            artist = explicit_artist
            title = full_title
        else:
            artist, title = self._parse_track(full_title)
        
        def _update():
            for key in session_keys:
                try:
                    net = self._get_user_network(key)
                    if net:
                        net.update_now_playing(artist=artist, title=title)
                except Exception as e:
                    print(f"Erro no Last.fm (Now Playing) para key {key[:5]}...: {e}")
                    
        await asyncio.to_thread(_update)

    async def scrobble(self, full_title: str, timestamp: int, session_keys: list[str], explicit_artist: str | None = None) -> None:
        if not session_keys:
            return
            
        if explicit_artist:
            artist = explicit_artist
            title = full_title
        else:
            artist, title = self._parse_track(full_title)
        
        def _scrobble():
            for key in session_keys:
                try:
                    net = self._get_user_network(key)
                    if net:
                        net.scrobble(artist=artist, title=title, timestamp=timestamp)
                except Exception as e:
                    print(f"Erro no Last.fm (Scrobble) para key {key[:5]}...: {e}")
                    
        await asyncio.to_thread(_scrobble)

lastfm_service = LastfmService()
