package com.team1.trading.api.security;

import com.auth0.jwt.exceptions.JWTVerificationException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Verifies JWT tokens for all routes under {@code /api/v1/}, before any controller runs.
 *
 * <p>This filter implements the story requirement that "every route under the API prefix is
 * answered for token validity once, before any controller runs."
 *
 * <p>If the token is valid, the verified {@link JwtClaims} are stored in the request so
 * downstream components (controllers, services) can access them via
 * {@link JwtRequestContext#getClaims()}.
 *
 * <p>All verification failures throw {@link JwtVerificationException}, which the
 * {@link GlobalExceptionHandler} catches and translates to AUTH-401 with an identical
 * response body for all four failure modes (missing header, wrong scheme, expired,
 * forged signature).
 */
@Component
public class JwtVerificationFilter extends OncePerRequestFilter {

    private final JwtValidator jwtValidator;

    public JwtVerificationFilter(JwtValidator jwtValidator) {
        this.jwtValidator = jwtValidator;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                     FilterChain filterChain) throws ServletException, IOException {
        try {
            String authorizationHeader = request.getHeader("Authorization");
            JwtClaims claims = jwtValidator.verify(authorizationHeader);
            
            // Store claims in request context so controllers and services can access them
            JwtRequestContext.setClaims(claims);
            
            filterChain.doFilter(request, response);
        } catch (JwtVerificationException e) {
            // Let GlobalExceptionHandler catch and convert to AUTH-401
            throw new JwtAuthenticationException("Token verification failed", e);
        } finally {
            JwtRequestContext.clear();
        }
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Only apply to /api/v1/ routes
        String path = request.getRequestURI();
        return !path.startsWith("/api/v1/");
    }
}
