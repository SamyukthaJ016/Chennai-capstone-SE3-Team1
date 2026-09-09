package com.team1.trading.api.controller;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.is;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class AccountReadIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    @DisplayName("Integration Flow: Read account details against seeded Postgres database")
    void testReadAccountIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/1")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id", is(1)))
                .andExpect(jsonPath("$.holderName", is("Aarav Mehta")));
    }

    @Test
    @DisplayName("Integration Flow: Read cash balance against seeded Postgres database")
    void testReadBalanceIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/1/balance")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accountId", is(1)))
                .andExpect(jsonPath("$.cashBalance", is(125000.00)));
    }

    @Test
    @DisplayName("Integration Flow: Read positions against portfolio_positions table")
    void testReadPositionsIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/1/positions")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("Integration Flow: Unknown account returns ACC-404 envelope")
    void testUnknownAccountIntegration() throws Exception {
        mockMvc.perform(get("/api/v1/accounts/999999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode", is("ACC-404")));
    }
}