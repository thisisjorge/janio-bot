import os
import logging
import asyncio
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

LOGGER = logging.getLogger(__name__)

# O escopo deve bater com o que foi autorizado (auth/drive.file)
SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_NAME = "Janiobot Music"

class DriveVaultService:
    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        self.service = None
        self.folder_id = None

    def start(self):
        if all([self.client_id, self.client_secret, self.refresh_token]):
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=self.refresh_token,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    token_uri="https://oauth2.googleapis.com/token",
                    scopes=SCOPES
                )
                self.service = build('drive', 'v3', credentials=creds)
                LOGGER.info("Google Drive API inicializada via OAuth 2.0.")
                
                # Procura ou cria a pasta base
                self._ensure_folder_exists()
                
                asyncio.create_task(self._cleanup_loop())
            except Exception as e:
                LOGGER.error(f"Falha ao inicializar Google Drive API: {e}")
        else:
            LOGGER.warning("Google Drive API não configurada. Faltam chaves no .env.")

    def _ensure_folder_exists(self):
        try:
            query = f"mimeType='application/vnd.google-apps.folder' and name='{FOLDER_NAME}' and trashed = false"
            results = self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            items = results.get('files', [])
            
            if not items:
                LOGGER.info(f"Pasta '{FOLDER_NAME}' não encontrada. Criando...")
                file_metadata = {
                    'name': FOLDER_NAME,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = self.service.files().create(body=file_metadata, fields='id').execute()
                self.folder_id = folder.get('id')
                LOGGER.info(f"Pasta '{FOLDER_NAME}' criada com sucesso (ID: {self.folder_id}).")
            else:
                self.folder_id = items[0]['id']
                LOGGER.info(f"Pasta '{FOLDER_NAME}' encontrada (ID: {self.folder_id}).")
        except Exception as e:
            LOGGER.error(f"Erro ao verificar/criar pasta do Drive: {e}")

    async def search_by_video_id(self, video_id: str) -> str | None:
        if not self.service or not self.folder_id:
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_search_by_video_id, video_id)

    def _sync_search_by_video_id(self, video_id: str) -> str | None:
        try:
            # Busca baseada no appProperties e se está na nossa pasta
            query = f"'{self.folder_id}' in parents and appProperties has {{ key='youtubeVideoId' and value='{video_id}' }} and trashed = false"
            results = self.service.files().list(
                q=query, spaces='drive', fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            if not items:
                return None
                
            file_id = items[0]['id']
            file_name = items[0]['name']
            
            ext = os.path.splitext(file_name)[1]
            if not ext:
                ext = ".mp3"
                
            output_path = f"/tmp/janiobot/{video_id}{ext}"
            os.makedirs("/tmp/janiobot", exist_ok=True)
            
            if os.path.exists(output_path):
                LOGGER.info(f"Arquivo {output_path} já existe no cache local.")
                return output_path

            LOGGER.info(f"Baixando {file_name} do Drive para {output_path}")
            request = self.service.files().get_media(fileId=file_id)
            
            with open(output_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                    
            LOGGER.info(f"Download concluído: {output_path}")
            return output_path
            
        except Exception as e:
            LOGGER.error(f"Erro ao buscar/baixar do Drive: {e}")
            return None

    async def upload_file(self, file_path: str, video_id: str, title: str) -> bool:
        if not self.service or not self.folder_id:
            return False
            
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_upload_file, file_path, video_id, title)

    def _sync_upload_file(self, file_path: str, video_id: str, title: str) -> bool:
        try:
            file_name = f"{video_id} - {title}.mp3"
            file_metadata = {
                'name': file_name,
                'parents': [self.folder_id],
                'appProperties': {
                    'youtubeVideoId': video_id,
                    'source': 'janiobot'
                }
            }
            media = MediaFileUpload(file_path, mimetype='audio/mpeg', resumable=True)
            
            LOGGER.info(f"Iniciando upload para o Drive: {file_name}")
            self.service.files().create(
                body=file_metadata, media_body=media, fields='id'
            ).execute()
            LOGGER.info("Upload concluído com sucesso!")
            return True
        except Exception as e:
            LOGGER.error(f"Erro ao fazer upload para o Drive: {e}")
            return False

    async def list_vault(self):
        if not self.service or not self.folder_id:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_list_vault)
        
    def _sync_list_vault(self):
        try:
            query = f"'{self.folder_id}' in parents and trashed = false"
            results = self.service.files().list(
                q=query, spaces='drive', fields='files(id, name, appProperties, size)'
            ).execute()
            return results.get('files', [])
        except Exception as e:
            LOGGER.error(f"Erro ao listar cofre: {e}")
            return []
            
    async def remove_by_video_id(self, video_id: str) -> bool:
        if not self.service or not self.folder_id:
            return False
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_remove_by_video_id, video_id)
        
    def _sync_remove_by_video_id(self, video_id: str) -> bool:
        try:
            query = f"'{self.folder_id}' in parents and appProperties has {{ key='youtubeVideoId' and value='{video_id}' }} and trashed = false"
            results = self.service.files().list(
                q=query, spaces='drive', fields='files(id)'
            ).execute()
            items = results.get('files', [])
            if not items:
                return False
                
            for item in items:
                self.service.files().delete(fileId=item['id']).execute()
            return True
        except Exception as e:
            LOGGER.error(f"Erro ao remover arquivo: {e}")
            return False

    async def _cleanup_loop(self):
        # Limpa arquivos no cache mais velhos que 24 horas
        ttl_seconds = 24 * 3600
        while True:
            try:
                folder = "/tmp/janiobot"
                if os.path.exists(folder):
                    now = asyncio.get_event_loop().time()
                    now_ts = __import__('time').time()
                    for filename in os.listdir(folder):
                        file_path = os.path.join(folder, filename)
                        if os.path.isfile(file_path):
                            mtime = os.path.getmtime(file_path)
                            if now_ts - mtime > ttl_seconds:
                                try:
                                    os.remove(file_path)
                                    LOGGER.info(f"Arquivo de cache expirado deletado: {file_path}")
                                except Exception as e:
                                    LOGGER.error(f"Falha ao deletar {file_path}: {e}")
            except Exception as e:
                LOGGER.error(f"Erro no loop de limpeza do cache: {e}")
            
            await asyncio.sleep(3600) # Roda a cada hora

drive_vault_service = DriveVaultService()
