package com.streamshield.api.stream;

import java.util.List;
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import com.streamshield.api.security.AuthenticatedUserService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/spring/streams")
public class StreamController {
    private final StreamRepository repository;
    private final AuthenticatedUserService authenticatedUserService;

    public StreamController(StreamRepository repository, AuthenticatedUserService authenticatedUserService) {
        this.repository = repository;
        this.authenticatedUserService = authenticatedUserService;
    }

    @GetMapping
    @PreAuthorize("hasAnyRole('ANALYST', 'ADMIN', 'SUPER_ADMIN')")
    public List<StreamResponse> listTenantStreams(@AuthenticationPrincipal Jwt jwt) {
        UUID tenantId = authenticatedUserService.requireActiveTenantUser(jwt);
        return repository.findAllByTenantIdOrderByChannelNameAsc(tenantId).stream()
                .map(stream -> new StreamResponse(
                        stream.getId(), stream.getPlatform(), stream.getChannelName(),
                        stream.isLive(), stream.getViewerCount()))
                .toList();
    }

    public record StreamResponse(UUID id, String platform, String channelName,
                                 boolean isLive, int viewerCount) {}
}
