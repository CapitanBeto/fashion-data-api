"""
Guarda/actualiza el archivo .txt de perfiles en Google Drive usando OAuth
con una cuenta personal de Google.

Setup (una sola vez):
1. En Google Cloud Console, crea un proyecto y habilita "Google Drive API".
2. Crea credenciales OAuth Client ID de tipo "Desktop app".
3. Descarga el JSON y guárdalo como `credentials.json` en la raíz del proyecto.
4. La primera vez que el servidor intente escribir en Drive, se abrirá un
   navegador para que inicies sesión y autorices el acceso. Tras eso se
   genera `token.json`, que se reutiliza (y refresca) en las siguientes
   ejecuciones sin volver a pedir login.

Variables de entorno opcionales:
- GDRIVE_FILE_NAME: nombre del archivo en Drive (default: instagram_perfiles.txt)
- GDRIVE_FOLDER_ID: id de la carpeta de Drive donde crear/buscar el archivo
  (si no se define, se usa la raíz de "Mi unidad")
"""

import io
import os
import re
import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

BASE_DIR = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = BASE_DIR / "credentials.json"
TOKEN_PATH = BASE_DIR / "token.json"

DRIVE_FILE_NAME = os.getenv("GDRIVE_FILE_NAME", "instagram_perfiles.txt")
DRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")

_service = None

_BLOCK_SPLIT_RE = re.compile(r"\n{3,}")
_USER_LINE_RE = re.compile(r"^USUARIO:\s*(.+)$", re.MULTILINE)


def _get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise RuntimeError(
                    "No se encontró credentials.json en la raíz del proyecto. "
                    "Descárgalo desde Google Cloud Console (OAuth Client ID "
                    "tipo 'Desktop app') y colócalo ahí."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())

    return creds


def _get_service():
    global _service
    if _service is None:
        _service = build("drive", "v3", credentials=_get_credentials())
    return _service


def _find_file_id() -> str | None:
    service = _get_service()
    query = f"name = '{DRIVE_FILE_NAME}' and trashed = false"
    if DRIVE_FOLDER_ID:
        query += f" and '{DRIVE_FOLDER_ID}' in parents"

    response = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = response.get("files", [])
    return files[0]["id"] if files else None


def _download_text(file_id: str) -> str:
    service = _get_service()
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue().decode("utf-8")


def _upload_text(text: str, file_id: str | None) -> str:
    service = _get_service()
    media = MediaIoBaseUpload(
        io.BytesIO(text.encode("utf-8")), mimetype="text/plain", resumable=True
    )

    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
        return file_id

    metadata = {"name": DRIVE_FILE_NAME, "mimeType": "text/plain"}
    if DRIVE_FOLDER_ID:
        metadata["parents"] = [DRIVE_FOLDER_ID]

    created = service.files().create(body=metadata, media_body=media, fields="id").execute()
    return created["id"]


def _parse_blocks(text: str) -> dict[str, str]:
    """Reconstruye {username: bloque_de_texto} a partir del contenido actual."""
    if not text.strip():
        return {}

    blocks: dict[str, str] = {}
    for raw_block in _BLOCK_SPLIT_RE.split(text.strip()):
        raw_block = raw_block.strip("\n")
        if not raw_block:
            continue
        match = _USER_LINE_RE.search(raw_block)
        if not match:
            continue
        blocks[match.group(1).strip()] = raw_block
    return blocks


def upsert_profiles(new_blocks: dict[str, str]) -> None:
    """
    Reemplaza el bloque de cada usuario en el archivo de Drive (o lo agrega
    si es nuevo), y sube el archivo completo actualizado.
    """
    if not new_blocks:
        return

    file_id = _find_file_id()
    current_text = _download_text(file_id) if file_id else ""

    blocks = _parse_blocks(current_text)
    blocks.update(new_blocks)

    final_text = "\n\n\n".join(blocks.values()) + "\n"
    _upload_text(final_text, file_id)
    logger.info("Archivo '%s' actualizado en Drive con %d perfiles.", DRIVE_FILE_NAME, len(blocks))