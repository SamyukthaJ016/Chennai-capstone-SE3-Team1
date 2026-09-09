package com.team1.trading.api.security;

import com.auth0.jwt.exceptions.JWTVerificationException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

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
 * <p>All verification failures (missing header, wrong scheme, expired, forged signature)
 * return HTTP 401 with identical error body, preventing attackers from enumerating
 * which validation step failed.
 */
@Component
public class JwtVerificationFilter extends OncePerRequestFilter {

    private final JwtValidator jwtValidator;
    private final ObjectMapper objectMapper;

    public JwtVerificationFilter(JwtValidator jwtValidator, ObjectMapper objectMapper) {
        this.jwtValidator = jwtValidator;
        this.objectMapper = objectMapper;
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
        } catch (JWTVerificationException e) {
            // JWT verification failed: send AUTH-401 response directly from filter
            // (servlet filters are outside Spring's exception handler)
            writeUnauthorizedResponse(response);
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

    /**
     * Writes a 401 Unauthorized response with the standard error envelope.
     * The response body is identical for all four failure modes (missing header, wrong scheme,
     * expired token, forged signature) so attackers cannot enumerate which validation failed.
     */
    private void writeUnauthorizedResponse(HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        
        Map<String, String> errorBody = new HashMap<>();
        errorBody.put("errorCode", "AUTH-401");
        errorBody.put("message", "Unauthorized");
        
        response.getWriter().write(objectMapper.writeValueAsString(errorBody));
    }
}
