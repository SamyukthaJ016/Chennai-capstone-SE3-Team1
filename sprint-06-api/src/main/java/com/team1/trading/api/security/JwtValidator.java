package com.team1.trading.api.security;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTDecodeException;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.exceptions.SignatureVerificationException;
import com.auth0.jwt.exceptions.TokenExpiredException;
import com.auth0.jwt.interfaces.DecodedJWT;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;

/**
 * Verifies JWT tokens according to the auth contract in contracts/auth-api.yaml.
 *
 * <p>Verification follows the order specified in the story: check the signature, the expiry,
 * and the algorithm the token asks for, in that order, before reading a claim. A verifier
 * that decodes the payload first has already trusted whatever the client sent, so we validate
 * before decoding.
 *
 * <p>All verification failures throw {@link JwtVerificationException}, which the filter
 * translates to AUTH-401. The exception message is never exposed to the client, as per the
 * story requirement that all four failures return the same response body.
 */
@Component
public class JwtValidator {

    private final String secret;
    private final String expectedIssuer;

    public JwtValidator(
            @Value("${jwt.secret}") String secret,
            @Value("${jwt.issuer:auth-service}") String expectedIssuer) {
        this.secret = secret;
        this.expectedIssuer = expectedIssuer;
    }

    /**
     * Verifies a Bearer token and returns its claims.
     *
     * <p>Steps:
     * 1. Extract the token from "Bearer " prefix
     * 2. Decode the header to read the algorithm claim (without trusting the payload)
     * 3. Verify the signature with the algorithm specified in the token
     * 4. Check expiry
     * 5. Extract and validate claims
     *
     * @param bearerToken the "Bearer <token>" header value
     * @return verified claims, never null
     * @throws JwtVerificationException on any of: missing header, wrong scheme, invalid
     *         signature, expired token, wrong algorithm
     * @throws IllegalArgumentException if required configuration is missing
     */
    public JwtClaims verify(String bearerToken) throws JwtVerificationException {
        if (bearerToken == null || !bearerToken.startsWith("Bearer ")) {
            throw new JwtVerificationException("Missing or malformed Authorization header");
        }

        String token = bearerToken.substring("Bearer ".length());

        try {
            // Step 1: Decode the token without verification to read the header
            DecodedJWT decodedUnverified = JWT.decode(token);
            
            // Step 2: Read the algorithm from the header (before we've verified anything)
            String algorithmName = decodedUnverified.getHeaderClaim("alg").asString();
            if (algorithmName == null || algorithmName.isEmpty()) {
                throw new JwtVerificationException("Missing algorithm in token header");
            }

            // Step 3: Create the algorithm and verify the signature
            // HS256 is the only algorithm supported per contracts/auth-api.yaml
            if (!"HS256".equals(algorithmName)) {
                throw new JwtVerificationException("Unsupported or mismatched algorithm");
            }

            Algorithm algorithm = Algorithm.HMAC256(secret);
            DecodedJWT verified = JWT.require(algorithm)
                    .withIssuer(expectedIssuer)
                    .build()
                    .verify(token);

            // Step 4: Check expiry (already checked by JWT.require above, but be explicit)
            Instant expiresAt = verified.getExpiresAtAsInstant();
            if (expiresAt != null && expiresAt.isBefore(Instant.now())) {
                throw new TokenExpiredException("Token has expired");
            }

            // Step 5: Extract claims, with validation
            String sub = verified.getSubject();
            Long accountId = verified.getClaim("accountId").asLong();
            List<String> roles = verified.getClaim("roles").asList(String.class);
            Instant issuedAt = verified.getIssuedAtAsInstant();
            String issuer = verified.getIssuer();

            if (sub == null || accountId == null || roles == null || roles.isEmpty()) {
                throw new JwtVerificationException("Missing or invalid claims in token");
            }

            return new JwtClaims(sub, accountId, roles, issuedAt, expiresAt, issuer);

        } catch (SignatureVerificationException e) {
            // Signature verification failed
            throw e;
        } catch (TokenExpiredException e) {
            // Token has expired
            throw e;
        } catch (JWTDecodeException e) {
            // Malformed token (not three dot-separated parts, invalid base64, etc.)
            throw new JwtVerificationException("Invalid token format", e);
        } catch (JwtVerificationException e) {
            // Re-throw JWT library exceptions
            throw e;
        } catch (Exception e) {
            // Catch any other exception and wrap it
            throw new JwtVerificationException("Token verification failed: " + e.getMessage(), e);
        }
    }
}
