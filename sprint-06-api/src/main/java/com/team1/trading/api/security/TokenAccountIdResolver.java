package com.team1.trading.api.security;

/**
 * Resolves the numeric {@code accountId} claim a token bears, so the service can enforce the
 * contract's reach rule: a valid token whose {@code accountId} claim does not match the account
 * being addressed is {@code ACC-403}.
 *
 * <p>Signature verification, expiry checks and the route-level filter that rejects missing or
 * invalid tokens ({@code AUTH-401}) are the JIRA 8 work against the provided auth stub. This
 * seam is where that filter plugs in; until then, the OSP-only reader extracts the claim from an
 * already-accepted header. A missing or unreadable header resolves to {@code null}, which the
 * services treat as "no token" and skip the reach check, keeping the slice tests database-free.
 */
public interface TokenAccountIdResolver {

    Long resolve(String authorizationHeader);
}