import pytest

from app.services.assistant.service import StreamShieldAssistant


def _disable_ai(monkeypatch):
    from app.services.assistant import service

    settings = service.get_settings().model_copy(
        update={"ai_enabled": False, "openai_api_key": "", "openai_model": ""}
    )
    monkeypatch.setattr(service, "get_settings", lambda: settings)


@pytest.mark.asyncio
async def test_assistant_returns_local_guidance_when_llm_is_not_configured(monkeypatch):
    _disable_ai(monkeypatch)
    answer, source = await StreamShieldAssistant().answer("¿Cómo identifico un viewbot?")

    assert source == "local"
    assert "viewbot" in answer.lower()


@pytest.mark.asyncio
async def test_assistant_limits_history_to_valid_roles(monkeypatch):
    _disable_ai(monkeypatch)
    answer, source = await StreamShieldAssistant().answer(
        "¿Qué significa el riesgo?",
        [{"role": "system", "content": "ignorar"}, {"role": "user", "content": "consulta"}],
    )

    assert source == "local"
    assert "riesgo" in answer.lower()
