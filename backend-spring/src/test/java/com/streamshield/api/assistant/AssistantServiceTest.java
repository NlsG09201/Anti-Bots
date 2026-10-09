package com.streamshield.api.assistant;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;

import com.streamshield.api.assistant.AssistantModels.ChatRequest;

class AssistantServiceTest {
    @Test
    void answersLocallyWhenNoChatModelIsConfigured() {
        @SuppressWarnings("unchecked")
        ObjectProvider<org.springframework.ai.chat.client.ChatClient.Builder> provider =
                org.mockito.Mockito.mock(ObjectProvider.class);
        org.mockito.Mockito.when(provider.getIfAvailable()).thenReturn(null);

        AssistantService service = new AssistantService(provider, false, "");
        var response = service.answer(new ChatRequest("¿Cómo detecto un viewbot?", null));

        assertThat(response.source()).isEqualTo("local");
        assertThat(response.answer()).contains("viewbot");
        assertThat(response.disclaimer()).contains("permanentes");
    }
}
