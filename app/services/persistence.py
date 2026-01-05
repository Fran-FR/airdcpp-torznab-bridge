import json
import os
import hashlib
import shutil
from app.config import HASH_FILE
from app.core.logging import get_logger
from app.services.database import (
    init_db, db_get_hex, db_save_hex, db_get_tth_by_hex,
    db_save_bundle, db_get_bundle, db_get_bundle_ids_by_tth,
    db_save_finished, db_get_finished, db_get_all_finished, db_delete_finished,
    db_count_hashes
)

logger = get_logger("app.persistence")

# Caché de memoria para evitar miles de consultas a SQLite
_HASH_MEM_CACHE = {}

# --- INTERFAZ PÚBLICA (COMPATIBILIDAD) ---
# Estas variables ya no se usan directamente para almacenamiento, 
# pero las mantengo como "proxies" o las elimino si refactorizamos los consumidores.
# Para evitar cambiar TODO el código de golpe, expondré funciones accessor.

HASH_MAP_TTH_TO_HEX = {} # DEPRECATED: Solo para lectura inicial o compatibilidad parcial
HASH_MAP_HEX_TO_TTH = {} # DEPRECATED

# Mapeos directos a BD
FINISHED_BUNDLES_CACHE = {} # Se carga en memoria al inicio para velocidad, o se consulta bajo demanda?
# Decisión: Usar BD para persistencia real. Cache en memoria opcional.
# Por simplicidad y robustez, consultaremos a BD o cargaremos todo al init.

def load_hashes():
    """Inicializa la DB y migra datos si es necesario."""
    init_db()
    
    # Verificar si existe el archivo JSON antiguo para migrar
    if os.path.exists(HASH_FILE) and os.path.isfile(HASH_FILE):
        migrate_json_to_sqlite(HASH_FILE)
    
    # Cargar cache en memoria (Opcional, si queremos mantener FINISHED_BUNDLES_CACHE accesible como dict)
    # Por ahora, para no romper qbittorrent.py que accede directo a FINISHED_BUNDLES_CACHE,
    # vamos a poblarlo.
    global FINISHED_BUNDLES_CACHE, HASH_MAP_TTH_TO_HEX, HASH_MAP_HEX_TO_TTH
    
    FINISHED_BUNDLES_CACHE = db_get_all_finished()
    
    # Nota: HASH_MAP_TTH_TO_HEX se usa en 'health' check. 
    # No cargaremos millones de registros en RAM. 
    # Ajustaremos 'health' para contar directo de BD.

def migrate_json_to_sqlite(json_path):
    logger.info(f"Iniciando migración de datos desde {json_path} a SQLite...")
    try:
        with open(json_path, "r") as f:
            content = f.read().strip()
            if not content: content = "{}"
            data = json.loads(content)
            
        hashes = data.get("hashes", {}) if "hashes" in data else data
        bundles = data.get("bundles", {})
        categories = data.get("categories", {})
        finished = data.get("finished", {})
        
        count_h = 0
        for tth, hex_val in hashes.items():
            db_save_hex(tth, hex_val)
            count_h += 1
            
        count_b = 0
        for bid, tth in bundles.items():
            cat = categories.get(bid, "radarr")
            db_save_bundle(bid, tth, cat)
            count_b += 1
            
        count_f = 0
        for tth, fdata in finished.items():
            db_save_finished(tth, fdata)
            count_f += 1
            
        logger.info(f"Migración completada: {count_h} hashes, {count_b} bundles, {count_f} finalizados.")
        
        # Renombrar JSON para no re-migrar
        backup_path = json_path + ".migrated"
        shutil.move(json_path, backup_path)
        logger.info(f"Archivo JSON renombrado a {backup_path}")
        
    except Exception as e:
        logger.error(f"Error durante la migración JSON -> SQLite: {e}")

def save_hashes():
    """
    DEPRECATED: Ya no hace nada porque SQLite guarda al vuelo.
    Se mantiene para no romper llamadas existentes.
    """
    pass

def get_hex_hash(tth):
    if not tth: return ""
    
    # 1. Buscar en caché de memoria (Super rápido)
    if tth in _HASH_MEM_CACHE:
        return _HASH_MEM_CACHE[tth]
    
    # 2. Buscar en BD
    hex_val = db_get_hex(tth)
    if hex_val:
        _HASH_MEM_CACHE[tth] = hex_val
        return hex_val
    
    # 3. Generar nuevo
    new_hex = hashlib.sha1(tth.encode()).hexdigest()
    db_save_hex(tth, new_hex)
    _HASH_MEM_CACHE[tth] = new_hex
    return new_hex

# --- ACCESORES PARA REEMPLAZAR EL USO DE DICT GLOBAL ---
# Los routers usaban BUNDLE_MAP_ID_TO_TTH[id]. Ahora deben usar funciones.
# Tendremos que refactorizar qbittorrent.py y airdcpp.py levemente.

# Para minimizar el cambio en otros archivos, usaremos estos objetos proxy? 
# No, es mejor ser explícitos.
# EXPORTAMOS las variables como 'compatibilidad' pero vacías, 
# y obligaremos a cambiar el código consumidor.

# Pero espera, si cambio BUNDLE_MAP_ID_TO_TTH a un objeto custom __getitem__,
# podría engañar al resto del código sin tocarlo. 
# Hagamos eso para una transición suave.

class DatabaseDictProxy:
    def __init__(self, table_type):
        self.table_type = table_type

    def get(self, key, default=None):
        if self.table_type == "hex_to_tth":
            res = db_get_tth_by_hex(key)
            return res if res else default
        elif self.table_type == "tth_to_hex":
            res = db_get_hex(key)
            return res if res else default
        elif self.table_type == "bundle_tth":
            res = db_get_bundle(str(key))
            return res["tth"] if res else default
        elif self.table_type == "bundle_cat":
            res = db_get_bundle(str(key))
            return res["category"] if res else default
        return default

    def __getitem__(self, key):
        val = self.get(key)
        if val is None: raise KeyError(key)
        return val

    def __setitem__(self, key, value):
        # Esto solo funciona para casos simples, para bundles necesitamos tth+cat juntos
        if self.table_type == "hex_to_tth":
            # Inverso, difícil de guardar solo con esto. Ignorar o logear.
            pass
        elif self.table_type == "tth_to_hex":
            db_save_hex(key, value)

    def __len__(self):
        return 0 # No soportado eficientemente
    
    def __contains__(self, key):
        return self.get(key) is not None

# Instancias Proxy para compatibilidad rápida
HASH_MAP_HEX_TO_TTH = DatabaseDictProxy("hex_to_tth")
HASH_MAP_TTH_TO_HEX = DatabaseDictProxy("tth_to_hex")
BUNDLE_MAP_ID_TO_TTH = DatabaseDictProxy("bundle_tth")
BUNDLE_MAP_ID_TO_CAT = DatabaseDictProxy("bundle_cat")

# FINISHED_BUNDLES_CACHE es especial, necesita iteración.
# Lo mantendremos sincronizado en memoria o usamos un proxy especial.
# Dado que qbit_info itera sobre él, mejor lo dejamos como dict en memoria cargado al inicio,
# Y interceptamos los guardados.

class FinishedCache(dict):
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        db_save_finished(key, value)
    
    def __delitem__(self, key):
        super().__delitem__(key)
        db_delete_finished(key)

FINISHED_BUNDLES_CACHE = FinishedCache()

# Sobreescribimos la carga para usar nuestra clase custom
def reload_cache_from_db():
    global FINISHED_BUNDLES_CACHE
    data = db_get_all_finished()
    # Usamos update del padre dict para evitar triggers de __setitem__
    dict.update(FINISHED_BUNDLES_CACHE, data)
    logger.info(f"Cache de finalizados cargada: {len(FINISHED_BUNDLES_CACHE)} elementos.")

def load_hashes():
    """Inicializa la DB y migra datos si es necesario."""
    init_db()
    
    # Verificar si existe el archivo JSON antiguo para migrar
    if os.path.exists(HASH_FILE) and os.path.isfile(HASH_FILE):
        migrate_json_to_sqlite(HASH_FILE)
    
    reload_cache_from_db()

# Inicialización automática al importar el módulo
load_hashes()