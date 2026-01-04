import threading

# Semáforo para limitar búsquedas simultáneas en AirDC++ (1 por sesión para evitar kicks)
GLOBAL_SEARCH_LOCK = threading.Semaphore(1)

# Lock para proteger la escritura del archivo de hashes (JSON)
FILE_LOCK = threading.Lock()
