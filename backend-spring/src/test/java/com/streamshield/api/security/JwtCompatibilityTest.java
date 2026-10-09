package com.streamshield.api.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.security.oauth2.jwt.JwsHeader;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import com.nimbusds.jose.proc.SecurityContext;

class JwtCompatibilityTest {
    private static final String SECRET = "test-secret-key-that-is-long-enough-for-hs256";

    @Test
    void acceptsAStreamShieldAccessTokenSignedWithHs256() {
        SecurityConfiguration configuration = new SecurityConfiguration();
        SecretKey key = key(SECRET);
        var decoder = configuration.jwtDecoder(key);
        var jwt = decoder.decode(token(key, "access"));

        assertThat(jwt.getClaimAsString("type")).isEqualTo("access");
        assertThat(jwt.getClaimAsString("role")).isEqualTo("analyst");
    }

    @Test
    void rejectsRefreshTokensOnProtectedApiRoutes() {
        SecurityConfiguration configuration = new SecurityConfiguration();
        SecretKey key = key(SECRET);
        var decoder = configuration.jwtDecoder(key);

        assertThatThrownBy(() -> decoder.decode(token(key, "refresh")))
                .isInstanceOf(BadJwtException.class);
    }

    private static String token(SecretKey key, String type) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .subject(UUID.randomUUID().toString())
                .id(UUID.randomUUID().toString().replace("-", ""))
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .claim("tenant_id", UUID.randomUUID().toString())
                .claim("role", "analyst")
                .claim("type", type)
                .build();
        JwtEncoder encoder = new NimbusJwtEncoder(
                new ImmutableSecret<SecurityContext>(key.getEncoded()));
        return encoder.encode(JwtEncoderParameters.from(
                JwsHeader.with(MacAlgorithm.HS256).build(), claims)).getTokenValue();
    }

    private static SecretKey key(String value) {
        return new SecretKeySpec(value.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
    }
}
