package com.team1.trading.api.security;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.util.Base64;

/**
 * Reads the {@code accountId} claim from a {@code Bearer} JWT header without any JWT library.
 *
 * <p>This is deliberately not a verifier. Authenticating the token and rejecting invalid ones is
 * JIRA 8 work; this component only extracts the claim so the reach check described in
 * contracts/trade-api.yaml can run today. The payload segment is base64url JSON after an HTTP
 * header and the token's own shape, so it decodes without new dependencies. Any failure returns
 * {@code null}, meaning the caller must not rely on the token.
 */
@Component
public class HeaderTokenAccountIdResolver implements TokenAccountIdResolver {

    private static final String BEARER_PREFIX = "Bearer ";

    private final ObjectMapper objectMapper;

    public HeaderTokenAccountIdResolver(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Long resolve(String authorizationHeader) {
        if (authorizationHeader == null
                || !authorizationHeader.regionMatches(true, 0, BEARER_PREFIX, 0, BEARER_PREFIX.length())) {
            return null;
        }
        try {
            String token = authorizationHeader.substring(BEARER_PREFIX.length());
            String[] segments = token.split("\\.");
            if (segments.length != 3) {
                return null;
            }
            JsonNode claims = objectMapper.readTree(segmentBytes(segments[1]));
            JsonNode accountId = claims.get("accountId");
            return accountId != null && accountId.isNumber() ? accountId.asLong() : null;
        } catch (Exception e) {
            return null;
        }
    }

    private static byte[] segmentBytes(String base64Url) {
        return Base64.getUrlDecoder().decode(pad(base64Url));
    }

    private static String pad(String base64Url) {
        StringBuilder padded = new StringBuilder(base64Url);
        while (padded.length() % 4 != 0) {
            padded.append('=');
        }
        return padded.toString();
    }
}