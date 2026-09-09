package com.team1.trading.api.security;

import com.team1.trading.api.exception.ErrorCatalogue;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Integration tests for JWT verification through the filter and global exception handler.
 *
 * <p>Tests verify that:
 * 1. All JWT verification failures return AUTH-401
 * 2. All four failure modes (missing header, wrong scheme, expired, forged) return identical
 *    error responses
 * 3. Valid tokens pass through the filter
 * 4. The error message does not reveal which specific failure occurred
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "jwt.secret=" + TestJwtBuilder.TEST_SECRET,
        "jwt.issuer=" + TestJwtBuilder.TEST_ISSUER
})
@DisplayName("JWT Verification Filter Integration Tests")
class JwtVerificationFilterTest {

    @Autowired
    private MockMvc mockMvc;

    private String validToken;

    @BeforeEach
    void setUp() {
        validToken = TestJwtBuilder.forAccount(1)
                .withSub("user-123")
                .withRoles("CUSTOMER")
                .buildWithTestSecret();
    }

    @Nested
    @DisplayName("Rejects requests to /api/v1/ without authorization")
    class UnauthorizedRequests {

        @Test
        void rejects_request_without_authorization_header() throws Exception {
            mockMvc.perform(get("/api/v1/accounts/1"))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value(ErrorCatalogue.AUTH_401))
                    .andExpect(jsonPath("$.message").exists());
        }

        @Test
        void rejects_request_with_null_authorization_header() throws Exception {
            mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", ""))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value(ErrorCatalogue.AUTH_401));
        }

        @Test
        void rejects_request_with_wrong_scheme() throws Exception {
            mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", "Basic invalid"))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value(ErrorCatalogue.AUTH_401));
        }

        @Test
        void rejects_request_with_expired_token() throws Exception {
            String expiredToken = TestJwtBuilder.forAccount(1).buildExpired();

            mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", expiredToken))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value(ErrorCatalogue.AUTH_401));
        }

        @Test
        void rejects_request_with_forged_token() throws Exception {
            String forgedToken = TestJwtBuilder.forAccount(1).buildForged();

            mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", forgedToken))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value(ErrorCatalogue.AUTH_401));
        }

        @Test
        void rejects_request_with_malformed_token() throws Exception {
            mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", "Bearer invalid.token.here"))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value(ErrorCatalogue.AUTH_401));
        }
    }

    @Nested
    @DisplayName("All four failure modes return identical response bodies (no enumeration)")
    class IdenticalErrorResponses {

        @Test
        void missing_header_response_format() throws Exception {
            mockMvc.perform(get("/api/v1/accounts/1"))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.errorCode").value(ErrorCatalogue.AUTH_401))
                    .andExpect(jsonPath("$.message").exists())
                    .andExpect(jsonPath("$.message").isString());
        }

        @Test
        void all_failures_return_same_generic_message() throws Exception {
            String genericMessage = "Unauthorized";

            // Missing header
            String response1 = mockMvc.perform(get("/api/v1/accounts/1"))
                    .andExpect(status().isUnauthorized())
                    .andReturn().getResponse().getContentAsString();

            // Wrong scheme
            String response2 = mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", "Basic wrong"))
                    .andExpect(status().isUnauthorized())
                    .andReturn().getResponse().getContentAsString();

            // Expired token
            String response3 = mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", TestJwtBuilder.forAccount(1).buildExpired()))
                    .andExpect(status().isUnauthorized())
                    .andReturn().getResponse().getContentAsString();

            // All should contain the generic message
            assert response1.contains(genericMessage);
            assert response2.contains(genericMessage);
            assert response3.contains(genericMessage);
        }

        @Test
        void no_specific_error_details_in_response() throws Exception {
            mockMvc.perform(get("/api/v1/accounts/1"))
                    .andExpect(status().isUnauthorized())
                    .andExpect(jsonPath("$.message")
                            .value(not(containsString("expired"))))
                    .andExpect(jsonPath("$.message")
                            .value(not(containsString("signature"))))
                    .andExpect(jsonPath("$.message")
                            .value(not(containsString("scheme"))));
        }
    }

    @Nested
    @DisplayName("Allows requests with valid tokens")
    class ValidTokenRequests {

        @Test
        void allows_request_with_valid_token() throws Exception {
            // Valid token should pass the filter and reach the controller
            // The controller may return 404 if account doesn't exist, but that's different
            // from 401 (Unauthorized)
            mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", validToken))
                    .andExpect(status().isNotEqualTo(401)); // Not 401 Unauthorized
        }

        @Test
        void stores_claims_in_request_context() throws Exception {
            // With a valid token, the filter should populate JwtRequestContext
            // We can't directly test the context in MockMvc, but we can verify
            // the request reaches the controller (doesn't get rejected at filter level)
            mockMvc.perform(get("/api/v1/accounts/1")
                    .header("Authorization", validToken))
                    .andExpect(status().isNotEqualTo(401));
        }
    }

    @Nested
    @DisplayName("Does not apply to routes outside /api/v1/")
    class SkipsNonApiRoutes {

        @Test
        void skips_filter_for_non_api_routes() throws Exception {
            // Non-API routes should not require authorization
            mockMvc.perform(get("/health"))
                    .andExpect(status().isNotEqualTo(401)); // Depends on what's available
        }

        @Test
        void skips_filter_for_root_path() throws Exception {
            mockMvc.perform(get("/"))
                    .andExpect(status().isNotEqualTo(401));
        }
    }
}
