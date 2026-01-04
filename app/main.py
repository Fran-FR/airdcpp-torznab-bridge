from fastapi import FastAPI, Request
from app.routers import general, torznab, qbittorrent
from app.services.airdcpp import AIRDCPP_URL, get_auth_headers
from app.core.logging import setup_logging, get_logger
import requests

# Inicializar logging
setup_logging()
logger = get_logger("app.main")

app = FastAPI(title="AirDC++ Torznab/qBit Bridge")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    host = request.headers.get("host", "localhost:8000")
    # logger.debug(f">>> REQ: {request.method} {request.url}") # Opcional: demasiado ruido para INFO
    response = await call_next(request)
    return response

@app.on_event("startup")
def startup_event():
    logger.info(f"--- Iniciando Test de Conectividad ---")
    logger.info(f"Objetivo: {AIRDCPP_URL}")
    headers = get_auth_headers()
    try:
        logger.info("> Enviando petición GET a /api/v1/hubs...")
        r = requests.get(f"{AIRDCPP_URL}/api/v1/hubs", headers=headers, timeout=2)
        logger.info(f"> Respuesta recibida: {r.status_code}")
        if r.status_code == 200:
            logger.info("Conexión con AirDC++ establecida correctamente.")
        else:
            logger.warning(f"AirDC++ respondió con status {r.status_code}. Revisa credenciales.")
    except Exception as e:
        logger.error(f"No se pudo contactar con AirDC++. Detalles: {e}")
    logger.info("--- Test de Conectividad Finalizado ---")

# Incluir routers
app.include_router(general.router)
app.include_router(torznab.router)
app.include_router(qbittorrent.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
