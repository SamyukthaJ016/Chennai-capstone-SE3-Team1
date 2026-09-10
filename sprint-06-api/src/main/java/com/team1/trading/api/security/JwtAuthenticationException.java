package com.team1.trading.api.security;

/**
 * Thrown when JWT verification fails. Caught by {GlobalExceptionHandler} and
 * translated to AUTH-401.
 */
public class JwtAuthenticationException extends RuntimeException {
    
    public JwtAuthenticationException(String message) {
        super(message);
    }

    public JwtAuthenticationException(String message, Throwable cause) {
        super(message, cause);
    }
}
