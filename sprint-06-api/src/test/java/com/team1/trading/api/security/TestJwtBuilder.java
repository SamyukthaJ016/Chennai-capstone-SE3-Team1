package com.team1.trading.api.security;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;

/**
 * Test fixture for minting signed JWT tokens.
 *
 * <p>Follows contracts/auth-api.yaml for claim names and types. All tokens are signed with
 * HS256 and a team-owned test secret. This fixture is not deployed as a service; it exists
 * only in the test suite to verify the production JWT verification code.
 *
 * <p>Example usage:
 * <pre>
 * String token = TestJwtBuilder.forAccount(1)
 *     .withSub("8f14e45f-ceea-4c1b-9d3b-1a2b3c4d5e6f")
 *     .withRoles("CUSTOMER")
 *     .expiresIn(15, ChronoUnit.MINUTES)
 *     .build("test-secret");
 * </pre>
 *
 * <p>When Sprint 8 adds the real auth service, only the configuration of the shared signing
 * secret changes; no code should move.
 */
public final class TestJwtBuilder {

    public static final String TEST_ISSUER = "auth-service";
    public static final String TEST_SECRET = "test-secret-key-for-sprint-6-jwt-verification-not-for-production";

    private final Long accountId;
    private String sub;
    private List<String> roles = List.of("CUSTOMER");
    private Instant issuedAt = Instant.now();
    private Instant expiresAt = Instant.now().plus(15, ChronoUnit.MINUTES);

    private TestJwtBuilder(Long accountId) {
        this.accountId = accountId;
        this.sub = "test-user-" + accountId;
    }

    /**
     * Create a builder for a token representing the given account.
     */
    public static TestJwtBuilder forAccount(Long accountId) {
        return new TestJwtBuilder(accountId);
    }

    /**
     * Set the {@code sub} claim (subject / user identifier). Defaults to "test-user-{accountId}".
     */
    public TestJwtBuilder withSub(String sub) {
        this.sub = sub;
        return this;
    }

    /**
     * Set the {@code roles} claim. Defaults to ["CUSTOMER"]. Must not be empty.
     */
    public TestJwtBuilder withRoles(String... roles) {
        this.roles = List.of(roles);
        if (this.roles.isEmpty()) {
            throw new IllegalArgumentException("roles must not be empty");
        }
        return this;
    }

    /**
     * Set the {@code roles} claim. Defaults to ["CUSTOMER"]. Must not be empty.
     */
    public TestJwtBuilder withRoles(List<String> roles) {
        if (roles.isEmpty()) {
            throw new IllegalArgumentException("roles must not be empty");
        }
        this.roles = roles;
        return this;
    }

    /**
     * Set the issued-at time. Defaults to now.
     */
    public TestJwtBuilder issuedAt(Instant issuedAt) {
        this.issuedAt = issuedAt;
        return this;
    }

    /**
     * Set the expiry as an absolute time. Defaults to 15 minutes from now.
     */
    public TestJwtBuilder expiresAt(Instant expiresAt) {
        this.expiresAt = expiresAt;
        return this;
    }

    /**
     * Set the expiry relative to now.
     */
    public TestJwtBuilder expiresIn(long amount, ChronoUnit unit) {
        this.expiresAt = Instant.now().plus(amount, unit);
        return this;
    }

    /**
     * Build the token and sign it with the test secret.
     *
     * @param secret the HS256 signing secret
     * @return a signed Bearer token ready to use in an Authorization header
     */
    public String build(String secret) {
        String token = JWT.create()
                .withSubject(sub)
                .withClaim("accountId", accountId)
                .withClaim("roles", roles)
                .withIssuedAt(issuedAt)
                .withExpiresAt(expiresAt)
                .withIssuer(TEST_ISSUER)
                .sign(Algorithm.HMAC256(secret));
        return "Bearer " + token;
    }

    /**
     * Build the token and sign it with the test secret. Equivalent to {@link #build(String)}.
     */
    public String buildWithTestSecret() {
        return build(TEST_SECRET);
    }

    /**
     * Build an unsigned token (no signature) for testing rejection of forged tokens.
     * The returned string is a valid JWT format but the signature is invalid.
     */
    public String buildForged() {
        // Create a token without any algorithm, then use a different secret to sign
        // This produces a token that looks valid but the signature won't verify
        String token = JWT.create()
                .withSubject(sub)
                .withClaim("accountId", accountId)
                .withClaim("roles", roles)
                .withIssuedAt(issuedAt)
                .withExpiresAt(expiresAt)
                .withIssuer(TEST_ISSUER)
                .sign(Algorithm.HMAC256("wrong-secret"));
        return "Bearer " + token;
    }

    /**
     * Build an expired token (expiry in the past).
     */
    public String buildExpired() {
        return issuedAt(Instant.now().minus(30, ChronoUnit.MINUTES))
                .expiresAt(Instant.now().minus(15, ChronoUnit.MINUTES))
                .buildWithTestSecret();
    }
}
