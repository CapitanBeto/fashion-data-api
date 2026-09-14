import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

from services.miapp import (
    get_post,
    get_profile,
    get_profiles,
)
from services.text_format import profiles_to_blocks
from services.gdrive_store import upsert_profiles

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Fashion Data API",
    version="1.0.0",
)


def _require_approval(approved: bool) -> None:
    """
    Rechaza el request si no viene explícitamente aprobado desde la app principal.
    Responde igual que una ruta inexistente (404 genérico, sin detalle) para no
    revelar que existe una validación de 'approved' ni por qué falló.
    """
    if not approved:
        raise HTTPException(status_code=404)


class InstagramProfileRequest(BaseModel):
    username: str
    approved: bool = False


class InstagramProfilesRequest(BaseModel):
    usernames: list[str]
    approved: bool = False


class InstagramPostRequest(BaseModel):
    url: str
    approved: bool = False


def _save_profiles_to_drive(profiles: list[dict]) -> None:
    """Transforma los perfiles al formato .txt y actualiza el archivo en Drive."""
    try:
        blocks = profiles_to_blocks(profiles)
        upsert_profiles(blocks)
    except Exception:
        logger.exception("Falló el guardado en Google Drive")


@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "fashion-data-api",
    }


@app.post("/instagram/profile")
async def instagram_profile(
    data: InstagramProfileRequest,
    background_tasks: BackgroundTasks,
):
    _require_approval(data.approved)

    try:
        result = await get_profile(data.username)
        if result:
            background_tasks.add_task(_save_profiles_to_drive, [result])
    except Exception:
        logger.exception("Falló get_profile para %s", data.username)

    return {"status": "ok"}


@app.post("/instagram/profiles")
async def instagram_profiles(
    data: InstagramProfilesRequest,
    background_tasks: BackgroundTasks,
):
    _require_approval(data.approved)

    try:
        result = await get_profiles(data.usernames)
        if result:
            background_tasks.add_task(_save_profiles_to_drive, result)
    except Exception:
        logger.exception("Falló get_profiles para %s", data.usernames)

    return {"status": "ok"}


@app.post("/instagram/post")
async def instagram_post(
    data: InstagramPostRequest,
    background_tasks: BackgroundTasks,
):
    _require_approval(data.approved)

    # El formato .txt de Drive está definido a nivel de perfil (USUARIO + sus
    # POSTs). Si más adelante quieres guardar posts sueltos ahí también,
    # dime el formato y lo agrego a text_format.py / gdrive_store.py.
    try:
        await get_post(data.url)
    except Exception:
        logger.exception("Falló get_post para %s", data.url)

    return {"status": "ok"}