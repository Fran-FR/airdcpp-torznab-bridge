# AirDC++ Bridge para Radarr y Sonarr

Este proyecto actúa como un puente (bridge) entre **AirDC++** y las aplicaciones de la familia *Arr (Radarr y Sonarr), emulando los APIs de qBittorrent (para descargas) y Torznab (para búsquedas).

## 🚀 Características Principales

- **Resolución de Títulos Avanzada**: Utiliza **TMDB** (TheMovieDB) y TVMaze para obtener nombres en español y alias exactos.
- **Normalización de Acentos**: Genera automáticamente variantes con y sin acentos para máxima compatibilidad con hubs.
- **Búsqueda Robusta**: Realiza búsquedas por nombre exacto y verifica el TTH para asegurar que descargas lo que elegiste.
- **Persistencia en SQLite**: Migración de JSON a una base de datos SQLite más robusta y eficiente.
- **Caché de XML**: Respuestas casi instantáneas para búsquedas repetitivas de Radarr/Sonarr.
- **Seguimiento en Tiempo Real**: API de qBittorrent optimizada para una importación instantánea y visibilidad completa de la cola.
- **Borrado Sincronizado**: Al borrar una descarga en Radarr/Sonarr, se elimina automáticamente del cliente AirDC++.

## 🛠️ Instalación y Uso

1. **Requisitos**: Tener Docker y Docker Compose instalados.
2. **Configuración**:
   - Crea un archivo `.env` basado en el `.env.example`.
   - **Importante**: Añade tu `TMDB_API_KEY` para la resolución de nombres en español.
3. **Levantar el servicio**:
   ```bash
   docker compose up -d --build
   ```

## ⚙️ Configuración en Radarr/Sonarr

### 1. Indexador (Torznab)
- **URL**: `http://tu-ip:8000/torznab`
- **API Key**: (Cualquier valor)
- **Categorías**: 5000 (TV), 2000 (Movies).

### 2. Cliente de Descarga (qBittorrent)
- **Host**: `tu-ip`
- **Puerto**: `8000`
- **Username/Password**: Los mismos configurados en el `.env`.
- **Categoría**: `radarr` o `sonarr`.

## 📁 Estructura del Proyecto

- `app/main.py`: Punto de entrada de la aplicación FastAPI.
- `app/routers/`: Definición de los endpoints (Torznab, qBittorrent, General).
- `app/services/`: Lógica de negocio (AirDC++, Base de Datos, Metadatos).
- `app/core/`: Configuración global, logging y bloqueos.
- `app/utils/`: Utilidades de texto y generación de XML.
- `data/bridge.db`: Base de datos SQLite (creada automáticamente).