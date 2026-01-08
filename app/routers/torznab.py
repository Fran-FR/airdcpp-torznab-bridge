import re
from fastapi import APIRouter, Request, Response, Query
from typing import Optional
from app.services.metadata import resolve_titles_by_id, resolve_titles_by_name
from app.services.airdcpp import search_airdcpp
from app.config import CAT_TO_PROFILE
from app.core.locks import GLOBAL_SEARCH_LOCK
from app.utils.xml import format_torznab_results, get_caps_xml, get_test_xml
from app.core.logging import get_logger
from app.services.cache import get_cached_search, set_cached_search

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
    # Clave de caché única
    cache_key = f"{t}_{q}_{cat}_{imdbid}_{tmdbid}_{tvdbid}_{season}_{ep}"
    
    # 1. Intentar recuperar de caché (RESPUESTA INSTANTÁNEA)
    cached_xml = get_cached_search(cache_key)
    if cached_xml is not None:
        logger.debug(f"Cache hit: {cache_key}")
        return Response(content=cached_xml, media_type="application/xml")

    logger.info(f"Torznab API request (t={t}): q='{q}', cat={cat}, season={season}, ep={ep}, imdb={imdbid}, tmdb={tmdbid}, tvdb={tvdbid}")
    
    if t == "caps":
        return Response(content=get_caps_xml().strip(), media_type="application/xml")
    
    if t in ["search", "tvsearch", "movie", "movie-search"]:
        detected_year = None
        if q and q.lower() != "none":
            # Detectar año en la query
            year_match = re.search(r'(?:\s|\()(\d{4})(?:\)|$)', q)
            if year_match:
                detected_year = year_match.group(1)
            
            # Limpiar patrones de temporada para búsquedas de TV
            if t == "tvsearch" or (cat and cat.startswith("5")):
                q = re.sub(r'\s[ST]\d{1,2}\b.*', '', q, flags=re.IGNORECASE).strip()

        # 1. Recolectar nombres base
        base_names = []
        if imdbid or tvdbid or tmdbid:
            base_names.extend(resolve_titles_by_id(imdbid=imdbid, tvdbid=tvdbid, tmdbid=tmdbid))
        
        if q and q.lower() != "none":
            if not base_names:
                base_names.extend(resolve_titles_by_name(q))
            if q not in base_names: base_names.append(q)

        # Normalización y deduplicación
        unique_bases = []
        seen = set()
        for b in base_names:
            b_low = b.lower().strip()
            if b_low not in seen:
                unique_bases.append(b)
                seen.add(b_low)

        if not unique_bases:
             return Response(content=get_test_xml().strip(), media_type="application/xml")

        # 2. Formatear queries finales
        final_queries = []
        is_season_search = (season is not None and ep is None)
        
        for base in unique_bases:
            if season and ep:
                final_queries.append(f"{base} S{season.zfill(2)}E{ep.zfill(2)}")
            elif season:
                final_queries.append(base)
            else:
                if detected_year and (t in ["movie", "movie-search"] or (cat and cat.startswith("2"))):
                    if not base.endswith(detected_year):
                        final_queries.append(f"{base} {detected_year}")
                final_queries.append(base)

        dedup_queries = list(dict.fromkeys(final_queries))
            
        with GLOBAL_SEARCH_LOCK:
            # Re-comprobar caché dentro del lock
            cached_xml = get_cached_search(cache_key)
            if cached_xml:
                return Response(content=cached_xml, media_type="application/xml")
                
            # Determinar perfil de filtrado por categoría
            profile = "video" # Default
            if cat:
                main_cat = cat.split(',')[0][0] # Primer dígito de la primera categoría
                profile = CAT_TO_PROFILE.get(main_cat, "generic")
                logger.debug(f"Categoría Torznab '{cat}' mapeada al perfil: {profile}")

            results = search_airdcpp(dedup_queries, is_season_search=is_season_search, season_num=season, cat_profile=profile)
            
            # Generar XML y guardar en caché
            host = request.headers.get("host", "localhost:8000")
            scheme = request.url.scheme
            base_url = f"{scheme}://{host}"
            xml_content = format_torznab_results(results, base_url, season=season, ep=ep).strip()
            set_cached_search(cache_key, xml_content)
            
        return Response(content=xml_content, media_type="application/xml")
    
    return Response(content="<error code='200' description='Not implemented' />", media_type="application/xml")