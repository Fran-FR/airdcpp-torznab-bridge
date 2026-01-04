# Análisis de Problemas y Mejoras - AirDC++ Torznab Bridge

Este documento detalla los problemas técnicos, de seguridad y de arquitectura detectados en el proyecto.

## 🔴 Problemas Críticos

### 1. Bloqueo del Event Loop (Rendimiento)
En `bridge.py`, la función `qbit_add` está definida como `async def`, pero utiliza la librería `requests` y `time.sleep()`, que son operaciones bloqueantes.
- **Impacto:** Durante una solicitud de descarga, todo el servidor se congela y deja de responder a otras peticiones (búsquedas, health checks).
- **Solución:** Cambiar a `def` sincronizada (para que FastAPI use un thread pool) o migrar a `httpx` con `await asyncio.sleep()`.

### 2. Credencial Expuesta (Seguridad)
La API Key de TMDB está escrita directamente en el código fuente (`TMDB_API_KEY`).
- **Impacto:** Riesgo de robo, abuso de cuota o revocación si el código se hace público.
- **Solución:** Mover la clave al archivo `.env` y cargarla mediante `os.getenv()`.

## 🟠 Problemas de Arquitectura y Mantenimiento

### 3. Código Monolítico
El archivo `bridge.py` contiene más de 600 líneas que mezclan lógica de API, scraping, persistencia y procesamiento de texto.
- **Impacto:** Difícil de testear, mantener y escalar.
- **Solución:** Refactorizar en módulos (ej. `api/`, `services/`, `utils/`).

### 4. Persistencia Frágil (JSON)
Se utiliza un archivo JSON con bloqueos manuales (`FILE_LOCK`).
- **Impacto:** Riesgo de corrupción de datos si el proceso se interrumpe durante una escritura. Rendimiento ineficiente para grandes volúmenes de datos.
- **Solución:** Migrar a **SQLite**, que es atómico y más robusto.

### 5. Sistema de Logs Inadecuado
Uso extensivo de `print()` en lugar del módulo `logging`.
- **Impacto:** Imposibilidad de filtrar logs por niveles (INFO, DEBUG, ERROR) o de integrarlos correctamente en sistemas de monitorización.
- **Solución:** Implementar `logging.getLogger(__name__)`.

## 🟡 Infraestructura y DevOps

### 6. Dependencias sin Versionar
El archivo `requirements.txt` no especifica versiones exactas de las librerías.
- **Impacto:** Una actualización de `fastapi` o `pydantic` podría romper el proyecto sin previo aviso.
- **Solución:** Fijar versiones (ej. `fastapi==0.109.0`).

### 7. Configuración de Docker para Desarrollo
El `docker-compose.yml` apunta a una imagen externa en lugar de permitir la construcción local para cambios rápidos.
- **Solución:** Habilitar la sección `build: .` comentada.
