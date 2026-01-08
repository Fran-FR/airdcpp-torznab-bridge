import os

# Configuración
AIRDCPP_URL = os.getenv("AIRDCPP_URL", "http://localhost:5600")
AIRDCPP_USER = os.getenv("AIRDCPP_USER", "")
AIRDCPP_PASS = os.getenv("AIRDCPP_PASS", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")

# Constantes
KNOWN_CATEGORIES = ["airdcpp", "radarr", "sonarr"]
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
HASH_FILE = os.path.join(DATA_DIR, "bridge_hashes.json")
