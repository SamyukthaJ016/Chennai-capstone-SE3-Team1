package com.team1.trading.api.controller;

import com.team1.trading.api.security.TestJwtBuilder;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "jwt.secret=" + TestJwtBuilder.TEST_SECRET,
        "jwt.issuer=" + TestJwtBuilder.TEST_ISSUER,
        "spring.datasource.url=jdbc:h2:mem:readintctx;DB_CLOSE_DELAY=-1"
})
class AccountReadIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    private String validToken;

    @BeforeEach
    void setUp() {
        validToken = TestJwtBuilder.forAccount(1L).buildWithTestSecret();
    }

    @Test
    @DisplayName("Integration Flow: Read account details against seeded database")
    void testReadAccountIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/1")
                        .header("Authorization", validToken)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id", is(1)))
                .andExpect(jsonPath("$.holderName", is("Aarav Mehta")));
    }

    @Test
    @DisplayName("Integration Flow: Read cash balance against seeded database")
    void testReadBalanceIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/1/balance")
                        .header("Authorization", validToken)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accountId", is(1)))
                .andExpect(jsonPath("$.cashBalance", is(125000.00)));
    }

    @Test
    @DisplayName("Integration Flow: Read positions against portfolio_positions table")
    void testReadPositionsIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/1/positions")
                        .header("Authorization", validToken)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("Integration Flow: Unknown account returns ACC-404 envelope")
    void testUnknownAccountIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/999999")
                        .header("Authorization", validToken)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode", is("ACC-404")));
    }
}