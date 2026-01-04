import re
from fastapi import APIRouter, Request, Response, Query
from typing import Optional
from app.services.metadata import resolve_titles_by_id, resolve_titles_by_name
from app.services.airdcpp import search_airdcpp
from app.core.locks import GLOBAL_SEARCH_LOCK
from app.utils.xml import format_torznab_results, get_caps_xml, get_test_xml
from app.core.logging import get_logger

logger = get_logger("app.routers.torznab")

router = APIRouter()

@router.get("/api")
@router.get("/torznab")
@router.get("/torznab/api")
def torznab_api(
    request: Request,
    t: str, 
    q: Optional[str] = None, 
    cat: Optional[str] = None,
    imdbid: Optional[str] = None,
    tmdbid: Optional[str] = None,
    tvdbid: Optional[str] = None,
    rid: Optional[str] = None,
    season: Optional[str] = None,
    ep: Optional[str] = None,
    apikey: Optional[str] = None
):
    # Log detallado de búsqueda para depuración
    logger.info(f"Torznab API request (t={t}): q='{q}', cat={cat}, season={season}, ep={ep}, imdb={imdbid}, tmdb={tmdbid}, tvdb={tvdbid}")
    
    if t == "caps":
        return Response(content=get_caps_xml().strip(), media_type="application/xml")
    if t in ["search", "tvsearch", "movie", "movie-search"]:
        # 0. Detectar año y LIMPIAR patrones de temporada
        detected_year = None
        if q and q.lower() != "none":
            # Busca un año de 4 dígitos entre espacios o paréntesis al final
            year_match = re.search(r'(?:\s|\()(\d{4})(?:\)|$)', q)
            if year_match:
                detected_year = year_match.group(1)
                logger.debug(f"Año detectado por regex en query: {detected_year}")
            
            # IMPORTANTE: Si es búsqueda de TV, quitamos patrones tipo S01, T01 para que el Hub encuentre de todo
            if t == "tvsearch" or (cat and cat.startswith("5")):
                q_old = q
                q = re.sub(r'\s[ST]\d{1,2}\b.*', '', q, flags=re.IGNORECASE).strip()
                if q != q_old:
                    logger.debug(f"Query TV limpiada de temporada: '{q_old}' -> '{q}'")

        # 1. Recolectar nombres base (Original + Traducidos)
        base_names = []
        if imdbid or tvdbid or tmdbid:
            base_names.extend(resolve_titles_by_id(imdbid=imdbid, tvdbid=tvdbid, tmdbid=tmdbid))
        
        if q and q.lower() != "none":
            if not base_names:
                base_names.extend(resolve_titles_by_name(q))
            if q not in base_names: base_names.append(q)

        # 2. Dedulplicar nombres base preservando caracteres (ñ, acentos)
        unique_bases = []
        seen_lowers = set()
        for name in base_names:
            low = name.lower().strip()
            if low and low not in seen_lowers:
                unique_bases.append(name.strip())
                seen_lowers.add(low)

        if not unique_bases:
             logger.warning(f"Búsqueda sin nombres resolubles (t={t}). Cancelando.")
             return Response(content=get_test_xml().strip(), media_type="application/xml")

        # 3. Formatear queries finales (Temporada/Episodio/Año)
        final_queries = []
        is_season_search = (season is not None and ep is None)
        
        for base in unique_bases:
            if season and ep:
                final_queries.append(f"{base} S{season.zfill(2)}E{ep.zfill(2)}")
            elif season:
                final_queries.append(base)
            else:
                is_movie = (t in ["movie", "movie-search"] or (cat and cat.startswith("2")))
                if detected_year and is_movie:
                    if not base.endswith(detected_year):
                        final_queries.append(f"{base} {detected_year}")
                    final_queries.append(base)
                else:
                    final_queries.append(base)

        # 4. Dedulplicar queries finales (orden preservado)
        dedup_queries = list(dict.fromkeys(final_queries))
            
        with GLOBAL_SEARCH_LOCK:
            results = search_airdcpp(dedup_queries, is_season_search=is_season_search, season_num=season)
        
        # Construimos el base_url
        host = request.headers.get("host", "localhost:8000")
        scheme = request.url.scheme
        base_url = f"{scheme}://{host}"
        
        xml_content = format_torznab_results(results, base_url, season=season, ep=ep).strip()
        return Response(content=xml_content, media_type="application/xml")
    
    return Response(content="<error code='200' description='Not implemented' />", media_type="application/xml")
