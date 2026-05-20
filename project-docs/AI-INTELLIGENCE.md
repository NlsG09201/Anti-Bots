# AI Intelligence System

Modular real-time AI for anti-viewbotting integrated into StreamShield.

## Architecture

```
Events → FeatureExtractor → FeatureStore (Redis)
                ↓
        InferenceEngine (5 models)
                ↓
        AIAssessment → ingest / WebSocket / API
                ↑
        FeedbackStore → TrainingPipeline (arq)
```

## Models

| Model | Purpose | Fallback |
|-------|---------|----------|
| `anomaly` | IsolationForest — behavioral outliers | Heuristic z-rules |
| `bot_classifier` | Bot vs human | RandomForest |
| `viewbot_predictor` | View inflation | GradientBoosting |
| `raid_predictor` | Raid / follow burst | GradientBoosting |
| `automation_detector` | Headless / webdriver | RandomForest |

Models persist to `data/ai_models/*.joblib`. Train via `POST /api/v1/ai-intel/train` or arq job `ai_train_models_job`.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/ai-intel/health` | Model status |
| `GET /api/v1/ai-intel/predictions` | Cached predictions per stream |
| `GET /api/v1/ai-intel/streams/{id}/prediction` | Single stream |
| `POST /api/v1/ai-intel/streams/{id}/assess` | Manual assess |
| `POST /api/v1/ai-intel/feedback` | Label true/false positive |
| `POST /api/v1/ai-intel/train` | Retrain models |

## Environment

```env
AI_INTEL_ENABLED=true
AI_INTEL_AUTO_MITIGATE=false
AI_INTEL_EARLY_WARNING_THRESHOLD=0.65
AI_MODEL_PATH=data/ai_models
MONGODB_URI=          # optional feature archive
```

## Dashboard

`/dashboard/ai` — predictions, threat levels, early warnings.

## Scale

- Inference: &lt;5ms heuristic, &lt;20ms with sklearn (cached features in Redis)
- Horizontal: stateless API + Redis feature windows + arq training workers
- Optional PyTorch: add `ai_intel/models/torch/` and register in `ModelRegistry`
