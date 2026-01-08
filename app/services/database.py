import sqlite3
import json
import os
from contextlib import contextmanager
from app.core.logging import get_logger

logger = get_logger("app.database")
# Ruta configurable vía entorno, por defecto la usada en el contenedor
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "bridge.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def db_cursor(commit=False):
    """Context manager para gestionar conexiones y transacciones de forma segura."""
    conn = get_db_connection()
    try:
        if commit:
            with conn:
                yield conn
        else:
            yield conn
    finally:
        conn.close()

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    if os.path.exists(DB_PATH):
        try:
            sizeKB = os.path.getsize(DB_PATH) / 1024
            logger.info(f"Archivo de base de datos detectado en {DB_PATH}: {sizeKB:.2f} KB")
        except Exception as e:
            logger.warning(f"No se pudo determinar el tamaño de la DB: {e}")
    else:
        logger.warning(f"No se detectó base de datos previa en {DB_PATH}. Se creará una nueva.")

    logger.info(f"Probando acceso a base de datos en: {os.path.abspath(DB_PATH)}")
    
    try:
        with db_cursor(commit=True) as conn:
            # Activar WAL mode para mejor concurrencia
            conn.execute("PRAGMA journal_mode=WAL;")
            
            # Tabla 1: Mapeo TTH <-> Hex
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hashes (
                    tth TEXT PRIMARY KEY,
                    hex TEXT UNIQUE NOT NULL
                );
            """)
            # Índice para buscar por hex rápido
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hashes_hex ON hashes(hex);")

            # Tabla 2: Bundles (Descargas activas/recientes)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bundles (
                    bundle_id TEXT PRIMARY KEY,
                    tth TEXT NOT NULL,
                    category TEXT DEFAULT 'radarr'
                );
            """)

            # Tabla 3: Descargas finalizadas (Cache para Radarr)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS finished (
                    tth TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                );
            """)
            
        logger.info(f"Base de datos inicializada en {DB_PATH}")
    except Exception as e:
        logger.error(f"Error inicializando base de datos: {e}")

# Funciones Helper para operaciones atómicas

def db_get_hex(tth):
    with db_cursor() as conn:
        row = conn.execute("SELECT hex FROM hashes WHERE tth = ?", (tth,)).fetchone()
        return row["hex"] if row else None

def db_save_hex(tth, hex_str):
    with db_cursor(commit=True) as conn:
        conn.execute("INSERT OR IGNORE INTO hashes (tth, hex) VALUES (?, ?)", (tth, hex_str))

def db_get_tth_by_hex(hex_str):
    with db_cursor() as conn:
        row = conn.execute("SELECT tth FROM hashes WHERE hex = ?", (hex_str,)).fetchone()
        return row["tth"] if row else None

def db_get_bundle(bundle_id):
    with db_cursor() as conn:
        row = conn.execute("SELECT tth, category FROM bundles WHERE bundle_id = ?", (bundle_id,)).fetchone()
        return dict(row) if row else None

def db_get_bundle_ids_by_tth(tth):
    with db_cursor() as conn:
        rows = conn.execute("SELECT bundle_id FROM bundles WHERE tth = ?", (tth,)).fetchall()
        return [r["bundle_id"] for r in rows]

def db_save_bundle(bundle_id, tth, category):
    with db_cursor(commit=True) as conn:
        conn.execute("INSERT OR REPLACE INTO bundles (bundle_id, tth, category) VALUES (?, ?, ?)", (bundle_id, tth, category))

def db_save_finished(tth, data_dict):
    json_str = json.dumps(data_dict)
    with db_cursor(commit=True) as conn:
        conn.execute("INSERT OR REPLACE INTO finished (tth, data) VALUES (?, ?)", (tth, json_str))

def db_get_finished(tth):
    with db_cursor() as conn:
        row = conn.execute("SELECT data FROM finished WHERE tth = ?", (tth,)).fetchone()
        if row:
            return json.loads(row["data"])
        return None

def db_get_all_finished():
    with db_cursor() as conn:
        rows = conn.execute("SELECT tth, data FROM finished").fetchall()
        results = {}
        for r in rows:
            results[r["tth"]] = json.loads(r["data"])
        return results

def db_delete_finished(tth):
    with db_cursor(commit=True) as conn:
        conn.execute("DELETE FROM finished WHERE tth = ?", (tth,))

def db_count_hashes():
    with db_cursor() as conn:
        row = conn.execute("SELECT Count(*) as count FROM hashes").fetchone()
        return row["count"] if row else 0
