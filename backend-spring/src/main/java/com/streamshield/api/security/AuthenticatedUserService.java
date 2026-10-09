package com.streamshield.api.security;

import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import com.streamshield.api.user.UserRepository;

@Service
public class AuthenticatedUserService {
    private final UserRepository users;
    private final StringRedisTemplate redis;
    private final boolean checkRedisBlacklist;

    public AuthenticatedUserService(
            UserRepository users,
            StringRedisTemplate redis,
            @Value("${streamshield.security.check-redis-blacklist:false}") boolean checkRedisBlacklist,
            @Value("${APP_ENV:development}") String environment,
            @Value("${REDIS_URL:}") String redisUrl) {
        if ("production".equalsIgnoreCase(environment)
                && (!checkRedisBlacklist || redisUrl == null || redisUrl.isBlank())) {
            throw new IllegalStateException(
                    "Production requires REDIS_URL and SPRING_CHECK_REDIS_BLACKLIST=true");
        }
        this.users = users;
        this.redis = redis;
        this.checkRedisBlacklist = checkRedisBlacklist;
    }

    public UUID requireActiveTenantUser(Jwt jwt) {
        UUID userId = parseClaim(jwt.getSubject());
        UUID tenantId = parseClaim(jwt.getClaimAsString("tenant_id"));
        if (users.findByIdAndTenantIdAndActiveTrue(userId, tenantId).isEmpty()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "User is inactive or tenant mismatch");
        }
        if (checkRedisBlacklist) {
            String tokenId = jwt.getId();
            if (tokenId == null || tokenId.isBlank()) {
                throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Token identifier is required");
            }
            try {
                Boolean revoked = redis.hasKey("ss:blacklist:" + tokenId);
                if (revoked == null) {
                    throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                            "Token revocation store returned no result");
                }
                if (revoked) {
                    throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Token has been revoked");
                }
            } catch (ResponseStatusException exception) {
                throw exception;
            } catch (RuntimeException exception) {
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                        "Token revocation store is unavailable", exception);
            }
        }
        return tenantId;
    }

    private static UUID parseClaim(String value) {
        try {
            return UUID.fromString(value);
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid identity claims");
        }
    }
}
