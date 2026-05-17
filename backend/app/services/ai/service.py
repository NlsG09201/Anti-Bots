from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class AIService:
    """Análisis de amenazas: OpenAI si hay clave; si no, heurísticas locales."""

    async def analyze_threat(
        self,
        attack_type: str,
        risk_score: float,
        channel_name: str,
        evidence: Dict[str, Any],
        monitor_mode: bool = False,
    ) -> Dict[str, Any]:
        if settings.ai_enabled and settings.openai_api_key:
            try:
                return await self._openai_analyze(
                    attack_type, risk_score, channel_name, evidence, monitor_mode
                )
            except Exception as exc:
                logger.warning("openai_analyze_failed", error=str(exc))
        return self._heuristic_analyze(attack_type, risk_score, channel_name, evidence, monitor_mode)

    def _heuristic_analyze(
        self,
        attack_type: str,
        risk_score: float,
        channel_name: str,
        evidence: Dict[str, Any],
        monitor_mode: bool,
    ) -> Dict[str, Any]:
        severity = "critical" if risk_score >= 85 else "high" if risk_score >= 70 else "medium" if risk_score >= 50 else "low"
        type_labels = {
            "viewbot": "viewbots",
            "followbot": "follow bots",
            "spam": "spam en chat",
            "coordinated": "ataque coordinado",
        }
        label = type_labels.get(attack_type, attack_type)
        summary = (
            f"Patrón de {label} detectado en {channel_name} con riesgo {risk_score:.0f}/100."
        )
        if evidence.get("coordination_score"):
            summary += f" Coordinación estimada: {evidence['coordination_score']:.0f}%."

        if monitor_mode:
            action = "observar"
            recommendation = (
                "Canal en modo monitoreo: no se aplicará mitigación automática en Twitch. "
                "Usa esta señal para validar reglas de detección."
            )
        elif risk_score >= 80:
            action = "ban"
            recommendation = "Bloquear IPs y usuarios implicados; revisar picos de viewers en los próximos 5 minutos."
        elif risk_score >= 65:
            action = "quarantine"
            recommendation = "Aislar sesiones sospechosas y activar captcha en nuevos joins."
        else:
            action = "monitor"
            recommendation = "Mantener correlación activa; confirmar con más eventos antes de banear."

        return {
            "summary": summary,
            "severity_assessment": severity,
            "recommended_action": action,
            "recommendation": recommendation,
            "confidence": min(risk_score / 100.0, 0.95),
            "source": "heuristic",
        }

    async def _openai_analyze(
        self,
        attack_type: str,
        risk_score: float,
        channel_name: str,
        evidence: Dict[str, Any],
        monitor_mode: bool,
    ) -> Dict[str, Any]:
        prompt = (
            f"Canal: {channel_name}. Tipo: {attack_type}. Riesgo: {risk_score}. "
            f"Modo monitoreo (sin mitigar en Twitch): {monitor_mode}. "
            f"Evidencia: {evidence}. "
            "Responde JSON con keys: summary, severity_assessment, recommended_action, recommendation, confidence (0-1)."
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Eres analista SOC de anti-bot para streaming. Respuestas breves en español, solo JSON válido.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
            import json

            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            data["source"] = "openai"
            return data
