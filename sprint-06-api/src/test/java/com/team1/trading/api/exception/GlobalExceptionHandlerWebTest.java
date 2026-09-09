package com.team1.trading.api.exception;

import com.team1.trading.domain.dto.PlaceOrderRequest;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.AuthenticationException;
import com.team1.trading.domain.exception.DuplicateOrderException;
import com.team1.trading.domain.exception.InstrumentNotFoundException;
import com.team1.trading.domain.exception.InsufficientFundsException;
import com.team1.trading.domain.exception.InsufficientHoldingsException;
import com.team1.trading.domain.exception.InvalidOrderException;
import com.team1.trading.domain.exception.OrderNotCancellableException;
import com.team1.trading.domain.exception.OrderNotFoundException;
import jakarta.validation.Valid;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Slice test proving that a real HTTP request which raises a domain exception leaves exactly
 * the error envelope {@code {"errorCode","message"}} and nothing else - no whitelabel page, no
 * stack trace, no empty body. Runs without a database or any other container.
 *
 * <p>The probe controller exists only inside this test; it is not deployed.
 */
@WebMvcTest(controllers = GlobalExceptionHandlerWebTest.EnvelopeProbeController.class)
class GlobalExceptionHandlerWebTest {

    @Autowired
    private MockMvc mockMvc;

    @Nested
    @DisplayName("Every failure leaves the error envelope over HTTP")
    class EnvelopeOverHttpTests {

        @Test
        @DisplayName("Account not found is HTTP 404 with ACC-404 and nothing else")
        void accountNotFound_envelope() throws Exception {
            expectEnvelope(get("/probe/account-not-found"),
                    HttpStatus.NOT_FOUND, "ACC-404", "Account not found");
        }

        @Test
        @DisplayName("Inactive account is HTTP 403 with ACC-403 and nothing else")
        void inactiveAccount_envelope() throws Exception {
            expectEnvelope(get("/probe/account-inactive"),
                    HttpStatus.FORBIDDEN, "ACC-403", "Account not active");
        }

        @Test
        @DisplayName("Unknown instrument is HTTP 404 with INS-404 and nothing else")
        void unknownInstrument_envelope() throws Exception {
            expectEnvelope(get("/probe/instrument-missing"),
                    HttpStatus.NOT_FOUND, "INS-404", "Instrument not found");
        }

        @Test
        @DisplayName("Insufficient funds is HTTP 400 with ORD-400 and nothing else")
        void insufficientFunds_envelope() throws Exception {
            expectEnvelope(get("/probe/insufficient-funds"),
                    HttpStatus.BAD_REQUEST, "ORD-400", "Insufficient funds");
        }

        @Test
        @DisplayName("Insufficient holdings is HTTP 409 with ORD-409 and nothing else")
        void insufficientHoldings_envelope() throws Exception {
            expectEnvelope(get("/probe/insufficient-holdings"),
                    HttpStatus.CONFLICT, "ORD-409", "Insufficient holdings");
        }

        @Test
        @DisplayName("Duplicate order is HTTP 409 with ORD-409 and nothing else")
        void duplicateOrder_envelope() throws Exception {
            expectEnvelope(get("/probe/duplicate-order"),
                    HttpStatus.CONFLICT, "ORD-409", "Duplicate order");
        }

        @Test
        @DisplayName("Invalid input is HTTP 422 with VAL-422 and nothing else")
        void invalidInput_envelope() throws Exception {
            expectEnvelope(get("/probe/invalid-input"),
                    HttpStatus.UNPROCESSABLE_ENTITY, "VAL-422", "Invalid input");
        }

        @Test
        @DisplayName("Bean validation on the request body is HTTP 422 with VAL-422")
        void beanValidation_envelope() throws Exception {
            expectEnvelope(post("/probe/invalid-request")
                            .contentType(MediaType.APPLICATION_JSON)
                            .content("{}"),
                    HttpStatus.UNPROCESSABLE_ENTITY, "VAL-422", "Invalid input");
        }

        @Test
        @DisplayName("An order that cannot be found is HTTP 404 but still ORD-409, exactly as the contract fixes")
        void orderNotFound_envelope() throws Exception {
            expectEnvelope(get("/probe/order-not-found"),
                    HttpStatus.NOT_FOUND, "ORD-409", "Order not found");
        }

        @Test
        @DisplayName("An order that is not cancellable is HTTP 409 with ORD-409")
        void orderNotCancellable_envelope() throws Exception {
            expectEnvelope(get("/probe/order-not-cancellable"),
                    HttpStatus.CONFLICT, "ORD-409", "Order is not cancellable");
        }

        @Test
        @DisplayName("A path or query value that fails conversion is HTTP 422 with VAL-422")
        void typeMismatch_envelope() throws Exception {
            expectEnvelope(get("/probe/type-mismatch").param("count", "abc"),
                    HttpStatus.UNPROCESSABLE_ENTITY, "VAL-422", "Invalid input");
        }

        @Test
        @DisplayName("A bad token is HTTP 401 with AUTH-401 and nothing else")
        void unauthenticated_envelope() throws Exception {
            expectEnvelope(get("/probe/unauthenticated"),
                    HttpStatus.UNAUTHORIZED, "AUTH-401", "Unauthorised");
        }

        @Test
        @DisplayName("An unexpected failure is still an envelope, never a whitelabel page")
        void unexpected_envelope() throws Exception {
            expectEnvelope(get("/probe/unexpected"),
                    HttpStatus.INTERNAL_SERVER_ERROR, "INTERNAL-500", "Internal error");
        }
    }

    private void expectEnvelope(MockHttpServletRequestBuilder request, HttpStatus status,
                                String code, String message) throws Exception {
        mockMvc.perform(request)
                .andExpect(status().is(status.value()))
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.errorCode").value(code))
                .andExpect(jsonPath("$.message").value(message))
                .andExpect(content().json(
                        "{\"errorCode\":\"" + code + "\",\"message\":\"" + message + "\"}",
                        true));
    }

    @RestController
    static class EnvelopeProbeController {

        @GetMapping("/probe/account-not-found")
        void accountNotFound() {
            throw new AccountNotFoundException(7L);
        }

        @GetMapping("/probe/account-inactive")
        void accountInactive() {
            throw new AccountNotActiveException(7L, "SUSPENDED");
        }

        @GetMapping("/probe/instrument-missing")
        void instrumentMissing() {
            throw new InstrumentNotFoundException("ACME");
        }

        @GetMapping("/probe/insufficient-funds")
        void insufficientFunds() {
            throw new InsufficientFundsException(7L, new BigDecimal("100.00"), new BigDecimal("50.00"));
        }

        @GetMapping("/probe/insufficient-holdings")
        void insufficientHoldings() {
            throw new InsufficientHoldingsException(7L, "ACME", new BigDecimal("10"), new BigDecimal("5"));
        }

        @GetMapping("/probe/duplicate-order")
        void duplicateOrder() {
            throw new DuplicateOrderException("6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e");
        }

        @GetMapping("/probe/invalid-input")
        void invalidInput() {
            throw new InvalidOrderException("quantity", 0);
        }

        @PostMapping("/probe/invalid-request")
        void invalidRequest(@Valid @RequestBody PlaceOrderRequest request) {
        }

        @GetMapping("/probe/order-not-found")
        void orderNotFound() {
            throw new OrderNotFoundException("ORD-6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e");
        }

        @GetMapping("/probe/order-not-cancellable")
        void orderNotCancellable() {
            throw new OrderNotCancellableException("ORD-6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e", "FILLED");
        }

        @GetMapping("/probe/type-mismatch")
        void typeMismatch(@RequestParam("count") int count) {
        }

        @GetMapping("/probe/unauthenticated")
        void unauthenticated() {
            throw new AuthenticationException("expired token");
        }

        @GetMapping("/probe/unexpected")
        void unexpected() {
            throw new IllegalStateException("unforeseen internal failure");
        }
    }
}