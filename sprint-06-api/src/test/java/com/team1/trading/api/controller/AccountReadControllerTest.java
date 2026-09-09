package com.team1.trading.api.controller;

import com.team1.trading.api.dto.AccountResponse;
import com.team1.trading.api.dto.BalanceResponse;
import com.team1.trading.api.dto.OrderHistoryEntry;
import com.team1.trading.api.dto.PositionResponse;
import com.team1.trading.api.security.TokenAccountIdResolver;
import com.team1.trading.api.service.AccountService;
import com.team1.trading.domain.entity.types.AccountStatus;
import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.is;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(AccountController.class)
class AccountReadControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private AccountService accountService;

    @MockitoBean
    private TokenAccountIdResolver tokenAccountIdResolver;

    private static final Long ACCOUNT_ID = 1L;

    @BeforeEach
    void setUp() {
        // Default behavior for resolver when no Authorization header is present
        given(tokenAccountIdResolver.resolve(any())).willReturn(null);
    }

    @Test
    @DisplayName("Path 1: Account, balance, positions and order history returned successfully")
    void testAllReadEndpointsSuccess() throws Exception {
        // Setup Account Response
        AccountResponse accountResponse = new AccountResponse(
                ACCOUNT_ID, "ACC-000001", "Aarav Mehta", new BigDecimal("485200.00"),
                AccountStatus.ACTIVE.name(), 0, LocalDateTime.now()
        );
        given(accountService.getAccount(eq(ACCOUNT_ID), any())).willReturn(accountResponse);

        mockMvc.perform(get("/api/v1/accounts/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id", is(1)))
                .andExpect(jsonPath("$.accountId", is("ACC-000001")))
                .andExpect(jsonPath("$.holderName", is("Aarav Mehta")));

        // Setup Balance Response
        BalanceResponse balanceResponse = new BalanceResponse(ACCOUNT_ID, new BigDecimal("485200.00"), "USD", LocalDateTime.now());
        given(accountService.getBalance(eq(ACCOUNT_ID), any())).willReturn(balanceResponse);

        mockMvc.perform(get("/api/v1/accounts/1/balance"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.accountId", is(1)))
                .andExpect(jsonPath("$.cashBalance", is(485200.00)))
                .andExpect(jsonPath("$.currency", is("USD")));

        // Setup Positions Response
        PositionResponse positionResponse = new PositionResponse(ACCOUNT_ID, "INFY", 100, new BigDecimal("1500.00"));
        given(accountService.getPositions(eq(ACCOUNT_ID), any())).willReturn(List.of(positionResponse));

        mockMvc.perform(get("/api/v1/accounts/1/positions"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].symbol", is("INFY")))
                .andExpect(jsonPath("$[0].quantity", is(100)))
                .andExpect(jsonPath("$[0].averageCost", is(1500.00)));

        // Setup Order History Response
        OrderHistoryEntry historyEntry = new OrderHistoryEntry(
                "ORD-12345", ACCOUNT_ID, "INFY", OrderSide.BUY, 100, new BigDecimal("1500.00"),
                new BigDecimal("1500.00"), OrderStatus.FILLED, "IDEM-1", LocalDateTime.now()
        );
        given(accountService.getOrderHistory(eq(ACCOUNT_ID), any(), any(), any(), any())).willReturn(List.of(historyEntry));

        mockMvc.perform(get("/api/v1/accounts/1/orders"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$", hasSize(1)))
                .andExpect(jsonPath("$[0].orderId", is("ORD-12345")));
    }

    @Test
    @DisplayName("Path 2: Unknown account returns ACC-404")
    void testUnknownAccountReturns404() throws Exception {
        given(accountService.getAccount(eq(999L), any())).willThrow(new AccountNotFoundException(999L));

        mockMvc.perform(get("/api/v1/accounts/999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode", is("ACC-404")))
                .andExpect(jsonPath("$.message", is("Account not found")));
    }

    @Test
    @DisplayName("Path 3: Token mismatch returns ACC-403")
    void testTokenMismatchReturns403() throws Exception {
        given(tokenAccountIdResolver.resolve("Bearer bad-token")).willReturn(5L);
        given(accountService.getAccount(eq(ACCOUNT_ID), eq(5L))).willThrow(new AccountNotActiveException(ACCOUNT_ID, "TOKEN"));

        mockMvc.perform(get("/api/v1/accounts/1")
                        .header("Authorization", "Bearer bad-token"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode", is("ACC-403")))
                .andExpect(jsonPath("$.message", is("Account not active")));
    }
}