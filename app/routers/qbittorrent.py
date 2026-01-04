import os
import time
import requests
from fastapi import APIRouter, Response, Query, Request, Form, File, UploadFile
from typing import Optional
from app.config import KNOWN_CATEGORIES, AIRDCPP_URL
from app.core.locks import GLOBAL_SEARCH_LOCK
from app.core.logging import get_logger
from app.services.persistence import (
    HASH_MAP_HEX_TO_TTH, HASH_MAP_TTH_TO_HEX, 
    FINISHED_BUNDLES_CACHE, BUNDLE_MAP_ID_TO_TTH, 
    BUNDLE_MAP_ID_TO_CAT, save_hashes, db_save_bundle
)
from app.services.airdcpp import get_auth_headers
from app.utils.text import clean_search_pattern

router = APIRouter()
logger = get_logger("app.routers.qbittorrent")

@router.get("/api/v2/app/version")
@router.get("/version/api") 
async def qbit_version():
    return Response(content="v4.3.9", media_type="text/plain")

@router.get("/api/v2/app/webApiVersion")
@router.get("/api/v2/app/webapiVersion")
async def qbit_webapi_version():
    return Response(content="2.8.2", media_type="text/plain")

@router.post("/api/v2/auth/login")
@router.post("/api/v2/auth/login/")
async def qbit_login(response: Response):
    response.set_cookie(key="SID", value="fake-session-id-12345")
    return Response(content="Ok.", media_type="text/plain")

@router.get("/api/v2/app/preferences")
async def qbit_preferences():
    return {
        "save_path": "/downloads",
        "listen_port": 8000
    }

@router.get("/api/v2/torrents/categories")
async def qbit_categories():
    return {cat: {"name": cat, "savePath": "/downloads"} for cat in KNOWN_CATEGORIES}

@router.post("/api/v2/torrents/createCategory")
async def qbit_create_category():
    return Response(content="Ok.", media_type="text/plain")

@router.post("/api/v2/torrents/setCategory")
async def qbit_set_category():
    return Response(content="Ok.", media_type="text/plain")

@router.get("/api/v2/torrents/properties")
async def qbit_properties(hash: str):
    return {
        "save_path": "/downloads",
        "creation_date": int(time.time()),
        "piece_size": 16384,
        "is_seed": True,
        "total_size": 0, 
    }

@router.get("/api/v2/torrents/files")
def qbit_files(hash: str):
    headers = get_auth_headers()
    tth = HASH_MAP_HEX_TO_TTH.get(hash, hash)
    
    r = requests.get(f"{AIRDCPP_URL}/api/v1/queue/bundles/0/1000", headers=headers, timeout=5)
    size = 0
    name = "unknown_file"
    if r.status_code == 200:
        for b in r.json():
            bundle_id = str(b["id"])
            if BUNDLE_MAP_ID_TO_TTH.get(bundle_id) == tth:
                size = int(float(b["size"]))
                name = b["name"]
                break
    
    return [{
        "name": name,
        "size": size,
        "progress": 1.0,
        "priority": 1,
        "is_seed": True,
        "piece_range_start": 0,
        "piece_range_end": 1,
        "availability": 1.0
    }]

@router.post("/api/v2/torrents/delete")
async def qbit_delete(hash: str = Query(None), hashes: str = Query(None)):
    target_hashes = []
    if hash: target_hashes.append(hash)
    if hashes: target_hashes.extend(hashes.split('|'))
    
    for h in target_hashes:
        tth = HASH_MAP_HEX_TO_TTH.get(h)
        if tth and tth in FINISHED_BUNDLES_CACHE:
            logger.info(f"Borrando {h} de FINISHED_BUNDLES_CACHE (Radarr terminó)")
            del FINISHED_BUNDLES_CACHE[tth]
            save_hashes()
            
    return Response(content="Ok.", media_type="text/plain")

def _get_qbit_info_internal(category: Optional[str] = None):
    headers = get_auth_headers()
    try:
        r = requests.get(f"{AIRDCPP_URL}/api/v1/queue/bundles/0/1000", headers=headers, timeout=5)
        bundles_in_queue = []
        if r.status_code == 200:
            bundles_in_queue = r.json()
        
        qbit_results = []
        reported_tths = set()
        
        req_cat = category.lower() if category else None
        
        needs_save = False
        for b in bundles_in_queue:
            bundle_id = str(b["id"])
            tth = BUNDLE_MAP_ID_TO_TTH.get(bundle_id)
            if not tth: continue
            
            bundle_cat = BUNDLE_MAP_ID_TO_CAT.get(bundle_id, "radarr").lower()
            if req_cat and bundle_cat != req_cat:
                continue
                
            reported_tths.add(tth)
            fake_hash = get_hex_hash(tth)
            size = int(float(b["size"]))
            downloaded = int(float(b.get("downloaded_bytes", 0)))
            progress = downloaded / size if size > 0 else 0
            
            status_obj = b.get("status", {})
            is_completed = status_obj.get("completed", False) or progress >= 0.999
            
            target_path = b.get("target", "").rstrip("/")
            if target_path:
                save_path, _ = os.path.split(target_path)
            else:
                save_path = "/downloads"
            
            completion_time = int(b.get("time_finished", 0))
            if is_completed and completion_time == 0:
                 completion_time = int(time.time())

            res_item = {
                "hash": fake_hash,
                "name": b["name"],
                "size": size,
                "progress": progress,
                "dlspeed": int(float(b.get("speed", 0))),
                "eta": int(float(b.get("seconds_left", 864000))),
                "state": "uploading" if is_completed else "downloading",
                "amount_left": max(0, size - downloaded),
                "completed": completion_time if is_completed else 0,
                "save_path": save_path,
                "label": bundle_cat,
                "category": bundle_cat,
                "num_seeds": 1 if is_completed else 0,
                "num_leechs": 0,
                "added_on": int(b.get("time_added", time.time())),
                "completion_on": completion_time if is_completed else 0
            }
            
            if is_completed:
                if tth not in FINISHED_BUNDLES_CACHE:
                    logger.info(f"Bundle {b['name']} marcado como completado en cache.")
                    needs_save = True
                FINISHED_BUNDLES_CACHE[tth] = res_item
                
            qbit_results.append(res_item)
            
        if needs_save:
            save_hashes()
            
        for tth, cached_item in FINISHED_BUNDLES_CACHE.items():
            if tth not in reported_tths:
                if req_cat and cached_item.get("category") != req_cat:
                    continue
                qbit_results.append(cached_item)
        
        return qbit_results
    except Exception as e:
        logger.error(f"Error en qbit_info: {e}")
        return []

@router.get("/api/v2/torrents/info")
def qbit_info(category: Optional[str] = None):
    return _get_qbit_info_internal(category)

@router.get("/api/v2/sync/maindata")
def qbit_maindata(category: Optional[str] = None):
    torrents = {}
    qbit_list = _get_qbit_info_internal(category=category)
    for t in qbit_list:
        torrents[t["hash"]] = t
        
    return {
        "torrents": torrents, 
        "full_update": True, 
        "categories": {cat: {"name": cat, "savePath": "/downloads"} for cat in KNOWN_CATEGORIES}
    }

@router.post("/api/v2/torrents/add")
def qbit_add(
    request: Request,
    urls: Optional[str] = Form(None),
    torrents: Optional[UploadFile] = File(None),
    category: Optional[str] = Form("radarr")
):
    headers = get_auth_headers()
    
    with GLOBAL_SEARCH_LOCK:
        logger.info(f"--- NUEVA SOLICITUD DE DESCARGA (qbit_add) ---")
    logger.debug(f"Headers: {dict(request.headers)}")
    
    url_list = []
    if urls:
        url_list = urls.split("\n")
    
    for url in url_list:
        url = url.strip()
        if not url: continue
        
        raw_hash = None
        if "tiger:" in url:
            raw_hash = url.split("tiger:")[1].split("&")[0]
        elif "btih:" in url:
            raw_hash = url.split("btih:")[1].split("&")[0]
            
        if raw_hash:
            tth = HASH_MAP_HEX_TO_TTH.get(raw_hash, raw_hash)
            
            if not tth or tth == "da39a3ee5e6b4b0d3255bfef95601890afd80709":
                continue

            instance_id = None
            try:
                name = "Unknown"
                if "dn=" in url:
                    name = url.split("dn=")[1].split("&")[0]
                
                logger.info(f"Procesando descarga robusta para: {name} (TTH: {tth})")
                
                res = requests.post(f"{AIRDCPP_URL}/api/v1/search", json={}, headers=headers, timeout=10)
                res.raise_for_status()
                instance_id = res.json()["id"]
                
                if tth.startswith("SYNTH:"):
                    parts = tth.split("SYNTH:")[1].rsplit(":", 1)
                    full_name = parts[0]
                    target_size_int = int(parts[1])
                    search_pattern = clean_search_pattern(full_name)
                    
                    search_payload = {"query": {"pattern": search_pattern}, "hub_urls": []}
                else:
                    search_payload = {"query": {"pattern": tth}, "hub_urls": []}
                
                requests.post(f"{AIRDCPP_URL}/api/v1/search/{instance_id}/hub_search", json=search_payload, headers=headers, timeout=10)
                
                results = []
                last_count = -1
                for i in range(15):
                    time.sleep(1)
                    max_results_to_fetch = 2000 if tth.startswith("SYNTH:") else 1
                    try:
                        results_res = requests.get(f"{AIRDCPP_URL}/api/v1/search/{instance_id}/results/0/{max_results_to_fetch}", headers=headers, timeout=5)
                        if results_res.status_code == 200:
                            current_results = results_res.json()
                            current_count = len(current_results)
                            results = current_results
                            if current_count > 0 and i > 6:
                                if current_count == last_count: break
                            last_count = current_count
                    except: continue
                
                selected_result = None
                if results:
                    if tth.startswith("SYNTH:"):
                        parts = tth.split("SYNTH:")[1].rsplit(":", 1)
                        target_name = parts[0]
                        target_size_int = int(parts[1])
                        
                        for r in results:
                            r_size_raw = r.get("size", 0)
                            r_size_int = int(float(r_size_raw))
                            r_name = r.get("name")
                            r_type_raw = r.get("type", "file")
                            r_type = r_type_raw.get("id", "file") if isinstance(r_type_raw, dict) else str(r_type_raw)
                            
                            if r_type not in ["directory", "bundle"] and r_size_int < 1024*1024*1024: continue

                            if r_size_int == target_size_int:
                                selected_result = r
                                break
                            
                            if r_size_int > 0 and abs(r_size_int - target_size_int) < 1024 * 1024:
                                if target_name[:10].lower() in r_name.lower():
                                    selected_result = r
                                    break
                    else:
                        selected_result = results[0]

                if selected_result:
                    result_id = selected_result["id"]
                    dl_res = requests.post(f"{AIRDCPP_URL}/api/v1/search/{instance_id}/results/{result_id}/download", json={"priority": 3}, headers=headers, timeout=10)
                    
                    if dl_res.status_code < 300:
                        dl_data = dl_res.json()
                        if "bundle_info" in dl_data:
                            new_bundle_id = str(dl_data["bundle_info"]["id"])
                            cat = category or "radarr"
                            if cat not in KNOWN_CATEGORIES: KNOWN_CATEGORIES.append(cat)
                            
                            # Guardado atómico en DB
                            db_save_bundle(new_bundle_id, tth, cat)
                            
                            logger.info(f"Mapeo guardado: Bundle {new_bundle_id} -> TTH {tth}")
                else:
                    logger.error(f"No se encontraron fuentes para TTH {tth}")
                    
            except Exception as e:
                logger.error(f"ERROR procesando {tth}: {e}")
            finally:
                if instance_id:
                    try: requests.delete(f"{AIRDCPP_URL}/api/v1/search/{instance_id}", headers=headers, timeout=5) 
                    except: pass
    
    return Response(content="Ok.", status_code=200, media_type="text/plain")
