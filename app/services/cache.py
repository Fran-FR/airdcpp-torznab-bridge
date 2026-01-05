import time
from typing import Dict, Any, Optional

# Almacén de búsquedas: { "query_key": {"timestamp": 12345, "results": [...]} }
_SEARCH_CACHE: Dict[str, Any] = {}
CACHE_TTL = 300 # 5 minutos de validez

def get_cached_search(query_key: str) -> Optional[list]:
    """Recupera resultados de caché si no han expirado."""
    entry = _SEARCH_CACHE.get(query_key)
    if entry:
        if time.time() - entry["timestamp"] < CACHE_TTL:
            return entry["results"]
        else:
            del _SEARCH_CACHE[query_key]
    return None

def set_cached_search(query_key: str, results: list):
    """Guarda resultados en caché con el timestamp actual."""
    _SEARCH_CACHE[query_key] = {
        "timestamp": time.time(),
        "results": results
    }

def clear_expired_cache():
    """Limpia entradas viejas."""
    now = time.time()
    to_delete = [k for k, v in _SEARCH_CACHE.items() if now - v["timestamp"] > CACHE_TTL]
    for k in to_delete:
        del _SEARCH_CACHE[k]
