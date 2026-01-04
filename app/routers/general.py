from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from app.services.persistence import HASH_MAP_TTH_TO_HEX, HASH_MAP_HEX_TO_TTH, db_count_hashes
from app.core.logging import get_logger

logger = get_logger("app.routers.general")

router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "hashes": db_count_hashes()}

@router.get("/download/{fake_hash}")
@router.get("/download/{fake_hash}.torrent") # Soportar ambas formas
async def download_redirect(fake_hash: str, name: str = "file"):
    logger.info(f"Radarr GRAB detectado para: {name} (Hex: {fake_hash})")
    
    # Strip .torrent if present
    if fake_hash.endswith(".torrent"):
        fake_hash = fake_hash[:-8]
        
    # tth = HASH_MAP_HEX_TO_TTH.get(fake_hash, fake_hash) # No se usa en magnet pero si en logica
    # También aquí para consistencia
    magnet = f"magnet:?xt=urn:btih:{fake_hash}&dn={name}&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337%2Fannounce"
    
    # Redirección 301 (Permanente) para máxima compatibilidad con el grabber de Radarr
    return RedirectResponse(url=magnet, status_code=301)
