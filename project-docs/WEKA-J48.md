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
| `weka` | Java 11+, `pip install weka-python3`, `JAVA_HOME` |
| `sklearn_j48_compat` | Solo scikit-learn (árbol entropía, sin Java) |

## Variables

- `WEKA_J48_ENABLED` — activar servicio
- `WEKA_J48_MODEL_PATH` — carpeta del modelo (`bot_j48.bundle.joblib`)
- `WEKA_J48_MIN_TRAINING_SAMPLES` — mínimo filas etiquetadas (default 50)
- `VIEWBOT_ML_ENABLED` — enriquecer lista de viewers con `j48_probability`

## Docker / Render

Para Weka nativo, añade JRE al contenedor:

```dockerfile
RUN apt-get update && apt-get install -y openjdk-17-jre-headless
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
RUN pip install weka-python3
```

Sin Java, el sistema usa el fallback sklearn automáticamente.

## API

- `GET /api/v1/ml/weka-j48/health`
- `GET /api/v1/ml/weka-j48/dataset/preview?source=mixed`
- `POST /api/v1/ml/weka-j48/train?limit=5000&source=mixed&include_twitch_insights=true`
- `GET /api/v1/ml/weka-j48/predict/session/{session_id}`
- `GET /api/v1/ml/weka-j48/predict/stream/{stream_id}`
