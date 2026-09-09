package com.team1.trading.api.security;

/**
 * ThreadLocal context for storing and retrieving JWT claims during request processing.
 *
 * <p>Set by {@link JwtVerificationFilter} after successful verification, and available
 * to controllers, services, and other request-scoped components. Automatically cleared
 * after the filter completes.
 */
public final class JwtRequestContext {

    private static final ThreadLocal<JwtClaims> claims = new ThreadLocal<>();

    private JwtRequestContext() {
    }

    public static void setClaims(JwtClaims jwtClaims) {
        claims.set(jwtClaims);
    }

    public static JwtClaims getClaims() {
        return claims.get();
    }

    public static void clear() {
        claims.remove();
    }
}
