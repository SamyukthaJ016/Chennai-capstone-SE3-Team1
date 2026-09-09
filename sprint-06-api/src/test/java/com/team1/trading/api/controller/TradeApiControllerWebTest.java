package com.team1.trading.api.controller;

import com.team1.trading.api.dto.AccountResponse;
import com.team1.trading.api.dto.BalanceResponse;
import com.team1.trading.api.dto.OrderHistoryEntry;
import com.team1.trading.api.dto.OrderResponse;
import com.team1.trading.api.dto.PositionResponse;
import com.team1.trading.api.security.JwtVerificationFilter;
import com.team1.trading.api.security.TokenAccountIdResolver;
import com.team1.trading.api.service.AccountService;
import com.team1.trading.api.service.OrderService;
import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.InsufficientFundsException;
import com.team1.trading.domain.exception.InvalidOrderException;
import com.team1.trading.domain.exception.OrderNotCancellableException;
import com.team1.trading.domain.exception.OrderNotFoundException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.nullable;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Slice test of the two {code /api/v1} controllers against the exact shapes of
 * contracts/trade-api.yaml. Services are mocked; the real {@code GlobalExceptionHandler}
 * keeps running, so a thrown domain exception and a body that fails validation both leave the
 * documented envelope over HTTP. No database or other container is started.
 */
@WebMvcTest(controllers = {OrderController.class, AccountController.class},
        excludeFilters = @ComponentScan.Filter(type = FilterType.ASSIGNABLE_TYPE, classes = JwtVerificationFilter.class))
@TestPropertySource(properties = {
    "jwt.secret=test-secret-key",
    "jwt.issuer=auth-service",
    "spring.datasource.url=jdbc:h2:mem:testdb",
    "spring.datasource.driver-class-name=org.h2.Driver"
})
class TradeApiControllerWebTest {

    private static final String IDEMPOTENCY_KEY = "6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e";
    private static final String ORDER_UUID = "6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e";

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @MockitoBean
    private AccountService accountService;

    @MockitoBean
    private TokenAccountIdResolver tokenAccountIdResolver;

    @Nested
    @DisplayName("POST /api/v1/orders")
    class PlaceOrderTests {

        @Test
        @DisplayName("A valid buy returns the Sprint 6 synchronous FILLED body, exactly the contract fields")
        void placeOrder_filledBody() throws Exception {
            given(orderService.placeOrder(any(), nullable(Long.class)))
                    .willReturn(new OrderResponse("ORD-" + ORDER_UUID, OrderStatus.FILLED, "Order executed",
                            "ACME", OrderSide.BUY, 100, new BigDecimal("25.50")));

            mockMvc.perform(post("/api/v1/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("""
                                    {"accountId":1,"symbol":"ACME","side":"BUY","quantity":100,
                                     "price":25.50,"idempotencyKey":"%s"}
                                    """.formatted(IDEMPOTENCY_KEY)))
                    .andExpect(status().isOk())
                    .andExpect(content().json("""
                            {"orderId":"ORD-%s","status":"FILLED","message":"Order executed",
                             "symbol":"ACME","side":"BUY","quantity":100,"price":25.50}
                            """.formatted(ORDER_UUID), true));
        }

        @Test
        @DisplayName("The token's accountId claim is resolved and passed to the service")
        void placeOrder_resolvesTokenClaim() throws Exception {
            given(tokenAccountIdResolver.resolve("Bearer eyJhbGciOiJub25lIn0.eyJhY2NvdW50SWQiOjd9.e30"))
                    .willReturn(7L);
            given(orderService.placeOrder(any(), nullable(Long.class)))
                    .willReturn(new OrderResponse("ORD-" + ORDER_UUID, OrderStatus.FILLED, "Order executed",
                            "ACME", OrderSide.BUY, 100, new BigDecimal("25.50")));

            mockMvc.perform(post("/api/v1/orders")
                            .header("Authorization", "Bearer eyJhbGciOiJub25lIn0.eyJhY2NvdW50SWQiOjd9.e30")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("""
                                    {"accountId":1,"symbol":"ACME","side":"BUY","quantity":100,
                                     "price":25.50,"idempotencyKey":"%s"}
                                    """.formatted(IDEMPOTENCY_KEY)))
                    .andExpect(status().isOk());

            verify(orderService).placeOrder(any(), eq(7L));
        }

        @Test
        @DisplayName("A body that fails field validation is HTTP 422 with VAL-422")
        void placeOrder_beanValidation() throws Exception {
            mockMvc.perform(post("/api/v1/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{}"))
                    .andExpect(status().isUnprocessableEntity())
                    .andExpect(content().json(
                            "{\"errorCode\":\"VAL-422\",\"message\":\"Invalid input\"}", true));
        }

        @Test
        @DisplayName("Insufficient funds from the service is HTTP 400 with ORD-400")
        void placeOrder_insufficientFunds() throws Exception {
            given(orderService.placeOrder(any(), nullable(Long.class)))
                    .willThrow(new InsufficientFundsException(1L, new BigDecimal("2550.00"), new BigDecimal("50.00")));

            mockMvc.perform(post("/api/v1/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("""
                                    {"accountId":1,"symbol":"ACME","side":"BUY","quantity":100,
                                     "price":25.50,"idempotencyKey":"%s"}
                                    """.formatted(IDEMPOTENCY_KEY)))
                    .andExpect(status().isBadRequest())
                    .andExpect(content().json(
                            "{\"errorCode\":\"ORD-400\",\"message\":\"Insufficient funds\"}", true));
        }

        @Test
        @DisplayName("A token that cannot reach the account is HTTP 403 with ACC-403")
        void placeOrder_tokenCannotReachAccount() throws Exception {
            given(orderService.placeOrder(any(), nullable(Long.class)))
                    .willThrow(new AccountNotActiveException(1L, "TOKEN"));

            mockMvc.perform(post("/api/v1/orders")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("""
                                    {"accountId":1,"symbol":"ACME","side":"BUY","quantity":100,
                                     "price":25.50,"idempotencyKey":"%s"}
                                    """.formatted(IDEMPOTENCY_KEY)))
                    .andExpect(status().isForbidden())
                    .andExpect(content().json(
                            "{\"errorCode\":\"ACC-403\",\"message\":\"Account not active\"}", true));
        }
    }

    @Nested
    @DisplayName("DELETE /api/v1/orders/{id}")
    class CancelOrderTests {

        @Test
        @DisplayName("A cancellable order returns CANCELLED with the contract body")
        void cancelOrder_cancelled() throws Exception {
            given(orderService.cancel(eq(ORDER_UUID), nullable(Long.class)))
                    .willReturn(new OrderResponse("ORD-" + ORDER_UUID, OrderStatus.CANCELLED, "Order cancelled",
                            "ACME", OrderSide.BUY, 100, new BigDecimal("25.50")));

            mockMvc.perform(delete("/api/v1/orders/{id}", ORDER_UUID))
                    .andExpect(status().isOk())
                    .andExpect(content().json("""
                            {"orderId":"ORD-%s","status":"CANCELLED","message":"Order cancelled",
                             "symbol":"ACME","side":"BUY","quantity":100,"price":25.50}
                            """.formatted(ORDER_UUID), true));
        }

        @Test
        @DisplayName("An unknown order is HTTP 404 with ORD-409 \"Order not found\", exactly as the contract fixes")
        void cancelOrder_notFound() throws Exception {
            given(orderService.cancel(eq(ORDER_UUID), nullable(Long.class)))
                    .willThrow(new OrderNotFoundException("ORD-" + ORDER_UUID));

            mockMvc.perform(delete("/api/v1/orders/{id}", ORDER_UUID))
                    .andExpect(status().isNotFound())
                    .andExpect(content().json(
                            "{\"errorCode\":\"ORD-409\",\"message\":\"Order not found\"}", true));
        }

        @Test
        @DisplayName("A terminal order is HTTP 409 with ORD-409 \"Order is not cancellable\"")
        void cancelOrder_notCancellable() throws Exception {
            given(orderService.cancel(eq(ORDER_UUID), nullable(Long.class)))
                    .willThrow(new OrderNotCancellableException("ORD-" + ORDER_UUID, "FILLED"));

            mockMvc.perform(delete("/api/v1/orders/{id}", ORDER_UUID))
                    .andExpect(status().isConflict())
                    .andExpect(content().json(
                            "{\"errorCode\":\"ORD-409\",\"message\":\"Order is not cancellable\"}", true));
        }
    }

    @Nested
    @DisplayName("GET /api/v1/accounts")
    class AccountReadTests {

        @Test
        @DisplayName("Account details carry the full contract body")
        void getAccount_body() throws Exception {
            given(accountService.getAccount(eq(1L), nullable(Long.class)))
                    .willReturn(new AccountResponse(1L, "ACC-000001", "Priya Menon",
                            new BigDecimal("24500.75"), "ACTIVE", 7,
                            LocalDateTime.of(2026, 9, 28, 9, 14, 22)));

            mockMvc.perform(get("/api/v1/accounts/{id}", 1L))
                    .andExpect(status().isOk())
                    .andExpect(content().json("""
                            {"id":1,"accountId":"ACC-000001","holderName":"Priya Menon",
                             "cashBalance":24500.75,"status":"ACTIVE","version":7,
                             "lastUpdated":"2026-09-28T09:14:22"}
                            """, true));
        }

        @Test
        @DisplayName("Balance carries accountId, cashBalance, currency and asOf")
        void getBalance_body() throws Exception {
            given(accountService.getBalance(eq(1L), nullable(Long.class)))
                    .willReturn(new BalanceResponse(1L, new BigDecimal("24500.75"), "USD",
                            LocalDateTime.of(2026, 9, 28, 9, 14, 22)));

            mockMvc.perform(get("/api/v1/accounts/{id}/balance", 1L))
                    .andExpect(status().isOk())
                    .andExpect(content().json("""
                            {"accountId":1,"cashBalance":24500.75,"currency":"USD",
                             "asOf":"2026-09-28T09:14:22"}
                            """, true));
        }

        @Test
        @DisplayName("Positions are a list of the contract's entries")
        void getPositions_body() throws Exception {
            given(accountService.getPositions(eq(1L), nullable(Long.class)))
                    .willReturn(List.of(
                            new PositionResponse(1L, "ACME", 100, new BigDecimal("25.50")),
                            new PositionResponse(1L, "INFY.NS", 40, new BigDecimal("1580.25"))));

            mockMvc.perform(get("/api/v1/accounts/{id}/positions", 1L))
                    .andExpect(status().isOk())
                    .andExpect(content().json("""
                            [{"accountId":1,"symbol":"ACME","quantity":100,"averageCost":25.50},
                             {"accountId":1,"symbol":"INFY.NS","quantity":40,"averageCost":1580.25}]
                            """, true));
        }

        @Test
        @DisplayName("Order history forwards the status, from and to filters to the service")
        void getOrders_forwardsFilters() throws Exception {
            given(accountService.getOrderHistory(anyLong(), nullable(Long.class),
                    nullable(String.class), nullable(LocalDateTime.class), nullable(LocalDateTime.class)))
                    .willReturn(List.of());

            mockMvc.perform(get("/api/v1/accounts/{id}/orders", 1L)
                            .param("status", "FILLED")
                            .param("from", "2026-09-28T00:00:00"))
                    .andExpect(status().isOk())
                    .andExpect(content().json("[]", true));

            verify(accountService).getOrderHistory(eq(1L), any(),
                    eq("FILLED"), eq(LocalDateTime.of(2026, 9, 28, 0, 0)), eq(null));
        }

        @Test
        @DisplayName("Order history entries serialise exactly as the contract defines")
        void getOrders_historyEntryBody() throws Exception {
            given(accountService.getOrderHistory(anyLong(), nullable(Long.class),
                    nullable(String.class), nullable(LocalDateTime.class), nullable(LocalDateTime.class)))
                    .willReturn(List.of(new OrderHistoryEntry("ORD-" + ORDER_UUID, 1L, "ACME",
                            OrderSide.BUY, 100, new BigDecimal("25.50"), new BigDecimal("25.50"),
                            OrderStatus.FILLED, IDEMPOTENCY_KEY, LocalDateTime.of(2026, 9, 28, 9, 14, 22))));

            mockMvc.perform(get("/api/v1/accounts/{id}/orders", 1L))
                    .andExpect(status().isOk())
                    .andExpect(content().json("""
                            [{"orderId":"ORD-%s","accountId":1,"symbol":"ACME","side":"BUY",
                              "quantity":100,"price":25.50,"executedPrice":25.50,
                              "status":"FILLED","idempotencyKey":"%s",
                              "createdOn":"2026-09-28T09:14:22"}]
                            """.formatted(ORDER_UUID, IDEMPOTENCY_KEY), true));
        }

        @Test
        @DisplayName("An unknown status value is HTTP 422 with VAL-422")
        void getOrders_invalidStatus() throws Exception {
            given(accountService.getOrderHistory(anyLong(), nullable(Long.class),
                    nullable(String.class), nullable(LocalDateTime.class), nullable(LocalDateTime.class)))
                    .willThrow(new InvalidOrderException("status", "BOGUS"));

            mockMvc.perform(get("/api/v1/accounts/{id}/orders", 1L)
                            .param("status", "BOGUS"))
                    .andExpect(status().isUnprocessableEntity())
                    .andExpect(content().json(
                            "{\"errorCode\":\"VAL-422\",\"message\":\"Invalid input\"}", true));
        }

        @Test
        @DisplayName("An unparseable from instant is HTTP 422 with VAL-422 before the service is called")
        void getOrders_unparseableFrom() throws Exception {
            mockMvc.perform(get("/api/v1/accounts/{id}/orders", 1L)
                            .param("from", "not-a-date"))
                    .andExpect(status().isUnprocessableEntity())
                    .andExpect(content().json(
                            "{\"errorCode\":\"VAL-422\",\"message\":\"Invalid input\"}", true));
        }

        @Test
        @DisplayName("A missing account is HTTP 404 with ACC-404")
        void getAccount_notFound() throws Exception {
            given(accountService.getAccount(eq(7L), nullable(Long.class)))
                    .willThrow(new AccountNotFoundException(7L));

            mockMvc.perform(get("/api/v1/accounts/{id}", 7L))
                    .andExpect(status().isNotFound())
                    .andExpect(content().json(
                            "{\"errorCode\":\"ACC-404\",\"message\":\"Account not found\"}", true));
        }
    }
}