package com.team1.trading.api.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Unit tests of the header claim reader. It only extracts the {@code accountId} claim; genuine
 * verification is JIRA 8 against the provided auth stub.
 */
class HeaderTokenAccountIdResolverTest {

    private HeaderTokenAccountIdResolver resolver;

    @BeforeEach
    void setUp() {
        resolver = new HeaderTokenAccountIdResolver(new ObjectMapper());
    }

    @Test
    @DisplayName("The accountId claim of a three-segment Bearer token is resolved")
    void resolvesClaim() {
        String token = tokenFor(Map.of("sub", "priya", "accountId", 7, "exp", 9999999999L));

        assertThat(resolver.resolve("Bearer " + token)).isEqualTo(7L);
    }

    @Test
    @DisplayName("The Bearer scheme is matched case-insensitively")
    void bearerSchemeIsCaseInsensitive() {
        String token = tokenFor(Map.of("accountId", 7));

        assertThat(resolver.resolve("bearer " + token)).isEqualTo(7L);
    }

    @Test
    @DisplayName("No header resolves to null")
    void missingHeader() {
        assertThat(resolver.resolve(null)).isNull();
    }

    @Test
    @DisplayName("A non-Bearer scheme resolves to null")
    void otherScheme() {
        assertThat(resolver.resolve("Basic dXNlcjpwYXNz")).isNull();
    }

    @Test
    @DisplayName("A token without the expected segment count resolves to null")
    void malformedSegmentCount() {
        assertThat(resolver.resolve("Bearer a.b")).isNull();
    }

    @Test
    @DisplayName("A payload without an accountId claim resolves to null")
    void noAccountIdClaim() {
        String token = tokenFor(Map.of("sub", "priya"));

        assertThat(resolver.resolve("Bearer " + token)).isNull();
    }

    @Test
    @DisplayName("Undecodable content resolves to null rather than throwing")
    void undecodablePayload() {
        assertThat(resolver.resolve("Bearer eyJhbGciOiJub25lIn0.!!!not-base64!!!.e30")).isNull();
    }

    private static String tokenFor(Map<String, Object> claims) {
        try {
            ObjectMapper mapper = new ObjectMapper();
            Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
            String header = encoder.encodeToString("{\"alg\":\"none\"}".getBytes(StandardCharsets.UTF_8));
            String payload = encoder.encodeToString(
                    mapper.writeValueAsBytes(claims));
            return header + "." + payload + ".e30";
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }
}