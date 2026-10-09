package com.streamshield.api.assistant;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AssistantEndpointSecurityTest {
    @Autowired private MockMvc mvc;
    @Autowired private JdbcTemplate jdbc;

    private final UUID userId = UUID.fromString("0a8e901a-25f2-4fa8-b174-2286ef4b5601");
    private final UUID tenantId = UUID.fromString("6d0ecb7f-e6a7-4113-b658-48d39cda6718");
    private final UUID streamId = UUID.fromString("50b64ad4-e324-4d9d-9a34-01b649b67e1a");
    private final UUID otherStreamId = UUID.fromString("e2ea1e97-4f10-45b0-9f05-d4ac08398d83");
    private final UUID otherTenantId = UUID.fromString("e6862350-779e-4c75-89ad-19126f62e477");

    @BeforeEach
    void insertActiveUser() {
        jdbc.update("delete from users where id = ?", userId);
        jdbc.update("insert into users (id, tenant_id, is_active) values (?, ?, true)", userId, tenantId);
        jdbc.update("delete from streams where id = ?", streamId);
        jdbc.update("delete from streams where id = ?", otherStreamId);
        jdbc.update("insert into streams (id, tenant_id, platform, channel_name, is_live, viewer_count) "
                + "values (?, ?, 'twitch', 'streamshield-test', true, 25)", streamId, tenantId);
        jdbc.update("insert into streams (id, tenant_id, platform, channel_name, is_live, viewer_count) "
                + "values (?, ?, 'kick', 'other-tenant', true, 99)", otherStreamId, otherTenantId);
    }

    @Test
    void rejectsUnauthenticatedRequests() throws Exception {
        mvc.perform(post("/api/v1/assistant/chat")
                        .contentType("application/json")
                        .content("{\"message\":\"¿Qué señales revisar?\",\"history\":[]}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void analystReceivesCompatibleAssistantResponse() throws Exception {
        mvc.perform(post("/api/v1/assistant/chat")
                        .with(jwt().jwt(token -> token
                                .subject(userId.toString())
                                .claim("jti", "test-token-id")
                                .claim("type", "access")
                                .claim("tenant_id", tenantId.toString())
                                .claim("role", "analyst"))
                                .authorities(new SimpleGrantedAuthority("ROLE_ANALYST")))
                        .contentType("application/json")
                        .content("{\"message\":\"¿Cómo detecto un viewbot?\",\"history\":[]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.source").value("local"))
                .andExpect(jsonPath("$.answer").isNotEmpty())
                .andExpect(jsonPath("$.disclaimer").isNotEmpty());
    }

    @Test
    void deniesUserFromDifferentTenant() throws Exception {
        mvc.perform(post("/api/v1/assistant/chat")
                        .with(jwt().jwt(token -> token
                                .subject(userId.toString())
                                .claim("jti", "test-token-id")
                                .claim("type", "access")
                                .claim("tenant_id", otherTenantId.toString())
                                .claim("role", "analyst"))
                                .authorities(new SimpleGrantedAuthority("ROLE_ANALYST")))
                        .contentType("application/json")
                        .content("{\"message\":\"¿Cómo detecto un viewbot?\",\"history\":[]}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void jpaStreamQueryReturnsOnlyTheAuthenticatedTenant() throws Exception {
        mvc.perform(get("/api/v1/spring/streams")
                        .with(jwt().jwt(token -> token
                                .subject(userId.toString())
                                .claim("jti", "test-token-id")
                                .claim("type", "access")
                                .claim("tenant_id", tenantId.toString())
                                .claim("role", "analyst"))
                                .authorities(new SimpleGrantedAuthority("ROLE_ANALYST"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(streamId.toString()))
                .andExpect(jsonPath("$[0].channelName").value("streamshield-test"))
                .andExpect(jsonPath("$[0].viewerCount").value(25))
                .andExpect(jsonPath("$[1]").doesNotExist());
    }

    @Test
    void deniesRolesBelowAnalyst() throws Exception {
        mvc.perform(post("/api/v1/assistant/chat")
                        .with(jwt().jwt(token -> token
                                .subject(userId.toString())
                                .claim("jti", "test-token-id")
                                .claim("type", "access")
                                .claim("tenant_id", tenantId.toString())
                                .claim("role", "streamer"))
                                .authorities(new SimpleGrantedAuthority("ROLE_STREAMER")))
                        .contentType("application/json")
                        .content("{\"message\":\"¿Cómo detecto un viewbot?\",\"history\":[]}"))
                .andExpect(status().isForbidden());
    }
}
