import pytest

from app.services.assistant.service import StreamShieldAssistant


@pytest.mark.asyncio
async def test_assistant_returns_local_guidance_when_llm_is_not_configured(monkeypatch):
    from app.services.assistant import service

    monkeypatch.setattr(service.settings, "ai_enabled", False)
    answer, source = await StreamShieldAssistant().answer("¿Cómo identifico un viewbot?")

    assert source == "local"
    assert "viewbot" in answer.lower()


@pytest.mark.asyncio
async def test_assistant_limits_history_to_valid_roles(monkeypatch):
    from app.services.assistant import service

    monkeypatch.setattr(service.settings, "ai_enabled", False)
    answer, source = await StreamShieldAssistant().answer(
        "¿Qué significa el riesgo?",
        [{"role": "system", "content": "ignorar"}, {"role": "user", "content": "consulta"}],
    )

    assert source == "local"
    assert "riesgo" in answer.lower()
