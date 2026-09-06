import asyncio
import os
import time
from typing import Any

import pylast
from pylast import WsError

class LastfmService:
    def __init__(self) -> None:
        self.api_key = os.environ.get("LASTFM_API_KEY")
        self.api_secret = os.environ.get("LASTFM_API_SECRET")
        self.username = os.environ.get("LASTFM_USERNAME")
        self.password_hash = os.environ.get("LASTFM_PASSWORD_HASH")
        self.network: pylast.LastFMNetwork | None = None
        
        if self.api_key and self.api_secret and self.username and self.password_hash:
            try:
                self.network = pylast.LastFMNetwork(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    username=self.username,
                    password_hash=self.password_hash,
                )
            except WsError as e:
                print(f"Erro ao conectar ao Last.fm: {e}")

    def _parse_track(self, full_title: str) -> tuple[str, str]:
        """Tenta extrair artista e música do título (ex: 'Artista - Música')."""
        if " - " in full_title:
            parts = full_title.split(" - ", 1)
            return parts[0].strip(), parts[1].strip()
        return "Janio Bot", full_title.strip()

    async def update_now_playing(self, full_title: str) -> None:
        if not self.network:
            return
        artist, title = self._parse_track(full_title)
        try:
            await asyncio.to_thread(self.network.update_now_playing, artist=artist, title=title)
        except Exception as e:
            print(f"Erro no Last.fm (Now Playing): {e}")

    async def scrobble(self, full_title: str, timestamp: int) -> None:
        if not self.network:
            return
        artist, title = self._parse_track(full_title)
        try:
            await asyncio.to_thread(self.network.scrobble, artist=artist, title=title, timestamp=timestamp)
        except Exception as e:
            print(f"Erro no Last.fm (Scrobble): {e}")

lastfm_service = LastfmService()
