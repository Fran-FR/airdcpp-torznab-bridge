import base64
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from app.config import AIRDCPP_URL, AIRDCPP_USER, AIRDCPP_PASS, KNOWN_CATEGORIES
from app.utils.text import normalize_text, clean_search_pattern
from app.services.persistence import BUNDLE_MAP_ID_TO_TTH, BUNDLE_MAP_ID_TO_CAT, save_hashes
from app.core.locks import GLOBAL_SEARCH_LOCK

from app.core.logging import get_logger

logger = get_logger("app.airdcpp")

def get_auth_headers():
    if AIRDCPP_USER and AIRDCPP_PASS:
        auth_str = f"{AIRDCPP_USER}:{AIRDCPP_PASS}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        return {"Authorization": f"Basic {encoded_auth}"}
    return {}

def search_airdcpp(query_or_list, is_season_search=False, season_num=None):
    headers = get_auth_headers()
    
    # Preparamos el regex para filtrar por temporada si es necesario
    season_regex = None
    if is_season_search and season_num:
        s_int = int(season_num)
        pattern = rf'(?:[ST]|Temporada|Season|Staffel|Temp|Pt|Part|P)\s*[.\-_]?\s*0?{s_int}\b'
        season_regex = re.compile(pattern, re.IGNORECASE)
        logger.info(f"Filtro regex para temporada {season_num} activado: {pattern}")
    
    queries_to_try = query_or_list if isinstance(query_or_list, list) else [query_or_list]

    # Expandir con fallbacks (quitar año)
    expanded_queries = []
    for q in queries_to_try:
        if not q: continue
        expanded_queries.append(q)
        match_year = re.search(r'\s(\d{4})$', q)
        if match_year:
            base_no_year = q.replace(match_year.group(0), "").strip()
            if base_no_year not in expanded_queries:
                expanded_queries.append(base_no_year)
            
    final_queries = list(dict.fromkeys(expanded_queries)) # Dedup preservando orden

    logger.info(f"Iniciando búsqueda AirDC++ con {len(final_queries)} variantes en paralelo")
    all_results = []
    
    def search_variant(q_attempt):
        variant_results = []
        try:
            logger.debug(f"Lanzando búsqueda paralela: '{q_attempt}'")
            res = requests.post(f"{AIRDCPP_URL}/api/v1/search", json={}, headers=headers, timeout=10)
            res.raise_for_status()
            instance_id = res.json()["id"]
            
            query_data = {"pattern": q_attempt}
            if is_season_search:
                query_data["type_id"] = "directory"
                query_data["size_min"] = 1024 * 1024 * 1024 # 1GB
            
            search_payload = {"query": query_data, "hub_urls": []}
            requests.post(f"{AIRDCPP_URL}/api/v1/search/{instance_id}/hub_search", json=search_payload, headers=headers, timeout=10)
            
            raw_results = []
            max_results = 2000
            last_stable_count = -1
            stable_cycles = 0
            
            for i in range(15):
                time.sleep(1)
                try:
                    results_res = requests.get(f"{AIRDCPP_URL}/api/v1/search/{instance_id}/results/0/{max_results}", headers=headers, timeout=5)
                    if results_res.status_code == 200:
                        current_results = results_res.json()
                        current_count = len(current_results)
                        raw_results = current_results
                        
                        if current_count > 0:
                            if current_count == last_stable_count:
                                stable_cycles += 1
                            else:
                                stable_cycles = 0
                                
                            if stable_cycles >= 4:
                                logger.debug(f"Búsqueda '{q_attempt}' estabilizada en {current_count} resultados.")
                                break
                        
                        last_stable_count = current_count
                except Exception:
                    continue
            
            requests.delete(f"{AIRDCPP_URL}/api/v1/search/{instance_id}", headers=headers, timeout=5)
            
            video_extensions = ('.mkv', '.avi', '.mp4', '.m4v', '.mov', '.wmv', '.mpg', '.mpeg')
            min_size = 100 * 1024 * 1024 if is_season_search else 50 * 1024 * 1024
            has_ep_pattern = re.search(r'[Ss]\d{2}[Ee]\d{2}', q_attempt)
            
            for r in raw_results:
                name_raw = r["name"]
                name_norm = normalize_text(name_raw)
                name_lower = name_raw.lower()
                
                raw_type = r.get("type", "file")
                item_type = raw_type.get("id", "file") if isinstance(raw_type, dict) else str(raw_type)
                size_bytes = int(r["size"])
                
                if is_season_search:
                    if item_type not in ["directory", "bundle"]: continue
                    clean_name = name_norm.replace("-", " ").replace(".", " ").replace("_", " ")
                    
                    if season_regex:
                        if not season_regex.search(clean_name): continue
                    
                    s_num = str(season_num or "").zfill(2)
                    display_season_tag = f"S{s_num}"
                    s_clean_pattern = rf'(?:[ST]|Temporada|Season|Staffel|Temp|Pt|Part|P)\s*[.\-_]?\s*0?{season_num}\b'

                    matched_alias = None
                    for q in final_queries:
                        if q.lower() in name_lower:
                            matched_alias = q
                            break

                    if matched_alias:
                        if display_season_tag.lower() in name_lower:
                            display_name = name_raw
                        else:
                            alias_lower = matched_alias.lower()
                            idx = name_lower.find(alias_lower) + len(alias_lower)
                            year_match = re.search(r'^\s*\(?\d{4}\)?', name_raw[idx:])
                            if year_match: idx += len(year_match.group(0))
                            
                            prefix = name_raw[:idx].strip()
                            suffix = name_raw[idx:].strip()
                            suffix = re.sub(s_clean_pattern, '', suffix, flags=re.IGNORECASE).strip()
                            suffix = re.sub(r'^[\s.\-_]+', '', suffix) 
                            
                            if suffix:
                                display_name = f"{prefix} {display_season_tag} {suffix}"
                            else:
                                display_name = f"{prefix} {display_season_tag}"
                    else:
                        name_cleaned = re.sub(s_clean_pattern, '', name_raw, flags=re.IGNORECASE).strip()
                        name_cleaned = re.sub(r'^[\s.\-_]+', '', name_cleaned)
                        
                        if name_cleaned:
                            display_name = f"{final_queries[0]} {display_season_tag} - {name_raw}"
                        else:
                            display_name = f"{final_queries[0]} {display_season_tag}"
                else:
                    if not name_lower.endswith(video_extensions): continue
                    display_name = name_raw
                
                if size_bytes < min_size: continue
                if has_ep_pattern and has_ep_pattern.group(0).lower() not in name_lower.replace(".", " ").replace("-", " "): continue
                
                tth = r.get("tth")
                if not tth:
                    if item_type in ["directory", "bundle"]:
                        tth = f"SYNTH:{display_name}:{size_bytes}"
                        logger.debug(f"Generado TTH sintético para carpeta: {tth}")
                    else:
                        continue
                        
                variant_results.append({"name": display_name, "size": size_bytes, "tth": tth})
                
        except Exception as e:
            logger.error(f"Error en variante '{q_attempt}': {e}")
        return variant_results

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for q in final_queries:
            futures.append(executor.submit(search_variant, q))
            time.sleep(2.5) 

    for f in futures:
        try:
            res_list = f.result()
            all_results.extend(res_list)
        except Exception as e:
            logger.error(f"Error recuperando resultados de futuro: {e}")

    unique_results = []
    seen_tths = set()
    for r in all_results:
        if r["tth"] not in seen_tths:
            unique_results.append(r)
            seen_tths.add(r["tth"])
            
    logger.info(f"Búsqueda finalizada: {len(unique_results)} resultados únicos totales")
    return unique_results
