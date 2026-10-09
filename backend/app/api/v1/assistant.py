"""API protegida del asistente conversacional del SOC."""

from fastapi import APIRouter

from app.api.dependencies import AnalystUser
from app.api.v1.schemas import AssistantChatRequest, AssistantChatResponse
from app.services.assistant.service import StreamShieldAssistant

router = APIRouter(prefix="/assistant", tags=["SOC Assistant"])
assistant_service = StreamShieldAssistant()


@router.post("/chat", response_model=AssistantChatResponse)
async def chat_with_assistant(
    payload: AssistantChatRequest,
    current_user: AnalystUser,
):
    """Consulta de solo lectura; exige rol analyst, admin o super_admin."""
    answer, source = await assistant_service.answer(
        payload.message,
        [message.model_dump() for message in payload.history],
    )
    return AssistantChatResponse(
        answer=answer,
        source=source,
        disclaimer="Orientación SOC; valida la evidencia antes de aplicar medidas permanentes.",
    )
