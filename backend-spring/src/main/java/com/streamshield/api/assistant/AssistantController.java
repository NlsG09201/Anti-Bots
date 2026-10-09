package com.streamshield.api.assistant;

import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.streamshield.api.assistant.AssistantModels.ChatRequest;
import com.streamshield.api.assistant.AssistantModels.ChatResponse;
import com.streamshield.api.security.AuthenticatedUserService;

import jakarta.validation.Valid;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@RestController
@RequestMapping(path = "/api/v1/assistant", produces = MediaType.APPLICATION_JSON_VALUE)
public class AssistantController {
    private final AssistantService assistantService;
    private final AuthenticatedUserService authenticatedUserService;

    public AssistantController(AssistantService assistantService, AuthenticatedUserService authenticatedUserService) {
        this.assistantService = assistantService;
        this.authenticatedUserService = authenticatedUserService;
    }

    @PostMapping(path = "/chat", consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAnyRole('ANALYST', 'ADMIN', 'SUPER_ADMIN')")
    public ChatResponse chat(@Valid @RequestBody ChatRequest request, @AuthenticationPrincipal Jwt jwt) {
        authenticatedUserService.requireActiveTenantUser(jwt);
        return assistantService.answer(request);
    }
}
