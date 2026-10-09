package com.streamshield.api.assistant;

import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public final class AssistantModels {
    private AssistantModels() {}

    public record HistoryMessage(
            @NotBlank @Pattern(regexp = "user|assistant") String role,
            @NotBlank @Size(max = 1000) String content) {}

    public record ChatRequest(
            @NotBlank @Size(max = 1000) String message,
            @Size(max = 6) List<@Valid HistoryMessage> history) {
        public ChatRequest {
            history = history == null ? List.of() : List.copyOf(history);
        }
    }

    public record ChatResponse(String answer, String source, String disclaimer) {}
}
