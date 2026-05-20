# Weka J48 — clasificador bot / humano

Pipeline que extrae features de `viewer_sessions` y `stream_events`, entrena un árbol **J48** (Weka) y predice si cada viewer es bot.

## Flujo

1. **Extracción** — `app/ml/weka_j48/sources.py` según la fuente elegida.
2. **Entrenamiento** — `POST /api/v1/ml/weka-j48/train?source=...` (admin) o job arq `weka_j48_train_job`.
3. **Inferencia** — `GET /api/v1/ml/weka-j48/predict/stream/{id}` o enriquecimiento en `GET /streams/{id}/viewers` (`j48_*`).

## Fuentes de entrenamiento (`source`)

| Valor | Qué usa |
|-------|---------|
| `registered_bots` | **Twitch Insights** (API viewbots), bans activos, fingerprints bloqueados, patrones locales (`malicious_db`, `pattern_db`), sesiones marcadas como bot |
| `channel_flow` | **Flujo en tus canales**: `stream_events` + `viewer_sessions`, veredictos IA en `behavior_metrics`, heurísticas por usuario |
| `mixed` | Combina ambas (recomendado) |

Vista previa antes de entrenar: `GET /api/v1/ml/weka-j48/dataset/preview?source=mixed`

## Backend

| Modo | Requisito |
|------|-----------|
| `weka` | Java 11+, `pip install python-weka-wrapper3`, JVM arrancada |
| `sklearn_j48_compat` | Solo scikit-learn (árbol entropía, sin Java) — fallback automático |

## Activar Weka Python

1. **Dependencia**: `python-weka-wrapper3==0.3.3` en `backend/requirements.txt`.
2. **Java**: 11+ (Docker instala OpenJDK 21 en Debian trixie; en Windows: Temurin 17/21 + opcional `WEKA_JAVA_HOME`).
3. **Variables**:
   - `WEKA_PYTHON_ENABLED=true`
   - `WEKA_JVM_EAGER_START=true` — arranca JVM al levantar la API
   - `WEKA_JVM_MAX_HEAP=512m`
   - `WEKA_J48_PREFER_WEKA=true`
4. **API admin**: `POST /api/v1/ml/weka-j48/jvm/start` — arranca JVM manualmente.
5. **Dashboard**: `/dashboard/weka` → botón **Activar Weka Python (JVM)**.
6. **Smoke test local**:
   ```bash
   cd backend && python scripts/check_weka.py
   ```

## Variables

- `WEKA_J48_ENABLED` — activar servicio
- `WEKA_PYTHON_ENABLED` — permitir JVM / Weka nativo
- `WEKA_JVM_EAGER_START` — precalentar JVM en startup
- `WEKA_JVM_MAX_HEAP` — heap JPype (ej. `512m`)
- `WEKA_J48_MODEL_PATH` — carpeta del modelo (`bot_j48.bundle.joblib`)
- `WEKA_JAVA_HOME` — ruta JDK si no está en PATH
- `WEKA_J48_MIN_TRAINING_SAMPLES` — mínimo filas etiquetadas (default 50)
- `VIEWBOT_ML_ENABLED` — enriquecer lista de viewers con `j48_probability`

## Docker / Render

El API en Render usa **runtime Docker** (`render.yaml`) con `backend/Dockerfile`:

- OpenJDK 21 JRE (`JAVA_HOME` preconfigurado en la imagen)
- `python-weka-wrapper3` instalado en build

Sin Java, el sistema usa el fallback sklearn automáticamente (`backend: sklearn_j48_compat`).

## API

- `GET /api/v1/ml/weka-j48/health` — `weka_python_installed`, `jvm_started`, `weka_runtime_ready`
- `POST /api/v1/ml/weka-j48/jvm/start` — admin, arranca JVM
- `GET /api/v1/ml/weka-j48/dataset/preview?source=mixed`
- `POST /api/v1/ml/weka-j48/train?limit=5000&source=mixed&include_twitch_insights=true`
- `GET /api/v1/ml/weka-j48/predict/session/{session_id}`
- `GET /api/v1/ml/weka-j48/predict/stream/{stream_id}`

## UI

- **Viewers** — columna J48 (`j48_is_bot`, `j48_probability`, `j48_backend`)
- **Weka J48** — `/dashboard/weka` — estado JVM, entrenar, predicciones por canal
