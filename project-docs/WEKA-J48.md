# Weka J48 — clasificador bot / humano

Pipeline que extrae features de `viewer_sessions` y `stream_events`, entrena un árbol **J48** (Weka) y predice si cada viewer es bot.

## Flujo

1. **Extracción** — `app/ml/weka_j48/dataset.py` carga sesiones del tenant (labels: `is_suspected_bot`, `risk_score`, bans activos).
2. **Entrenamiento** — `POST /api/v1/ml/weka-j48/train` (admin) o job arq `weka_j48_train_job`.
3. **Inferencia** — `GET /api/v1/ml/weka-j48/predict/stream/{id}` o enriquecimiento automático en `GET /streams/{id}/viewers` (`j48_*`).

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
- `POST /api/v1/ml/weka-j48/train?limit=5000`
- `GET /api/v1/ml/weka-j48/predict/session/{session_id}`
- `GET /api/v1/ml/weka-j48/predict/stream/{stream_id}`
