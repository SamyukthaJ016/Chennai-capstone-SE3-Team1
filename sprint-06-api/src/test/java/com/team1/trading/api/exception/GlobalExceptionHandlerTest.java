package com.team1.trading.api.exception;

import com.team1.trading.api.dto.ErrorResponse;
import com.team1.trading.domain.dto.PlaceOrderRequest;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.AuthenticationException;
import com.team1.trading.domain.exception.DomainException;
import com.team1.trading.domain.exception.DuplicateOrderException;
import com.team1.trading.domain.exception.InstrumentNotFoundException;
import com.team1.trading.domain.exception.InsufficientFundsException;
import com.team1.trading.domain.exception.InsufficientHoldingsException;
import com.team1.trading.domain.exception.InvalidOrderException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;

import java.lang.reflect.Field;
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Nested
    @DisplayName("Catalogue - every documented code maps to its HTTP status")
    class CatalogueTests {

        @Test
        @DisplayName("ACC-404 is served under 404")
        void acc404_mapsTo404() {
            assertStatusFor("ACC-404", HttpStatus.NOT_FOUND);
        }

        @Test
        @DisplayName("ACC-403 is served under 403")
        void acc403_mapsTo403() {
            assertStatusFor("ACC-403", HttpStatus.FORBIDDEN);
        }

        @Test
        @DisplayName("INS-404 is served under 404")
        void ins404_mapsTo404() {
            assertStatusFor("INS-404", HttpStatus.NOT_FOUND);
        }

        @Test
        @DisplayName("ORD-400 is served under 400")
        void ord400_mapsTo400() {
            assertStatusFor("ORD-400", HttpStatus.BAD_REQUEST);
        }

        @Test
        @DisplayName("ORD-409 is served under 409")
        void ord409_mapsTo409() {
            assertStatusFor("ORD-409", HttpStatus.CONFLICT);
        }

        @Test
        @DisplayName("VAL-422 is served under 422")
        void val422_mapsTo422() {
            assertStatusFor("VAL-422", HttpStatus.UNPROCESSABLE_ENTITY);
        }

        @Test
        @DisplayName("AUTH-401 is served under 401")
        void auth401_mapsTo401() {
            assertStatusFor("AUTH-401", HttpStatus.UNAUTHORIZED);
        }

        private void assertStatusFor(String code, HttpStatus expected) {
            assertEquals(expected, ErrorCatalogue.statusFor(code), "status for " + code);
        }
    }

    @Nested
    @DisplayName("Execution paths - the six documented failures")
    class ExecutionPathTests {

        @Test
        @DisplayName("Account not found maps to ACC-404 with status 404")
        void accountNotFound_mapsToAcc404() {
            assertDomainEnvelope(
                    new AccountNotFoundException(7L),
                    "ACC-404", HttpStatus.NOT_FOUND, "Account not found");
        }

        @Test
        @DisplayName("Inactive account maps to ACC-403 with status 403")
        void inactiveAccount_mapsToAcc403() {
            assertDomainEnvelope(
                    new AccountNotActiveException(7L, "SUSPENDED"),
                    "ACC-403", HttpStatus.FORBIDDEN, "Account not active");
        }

        @Test
        @DisplayName("Unknown instrument maps to INS-404 with status 404")
        void unknownInstrument_mapsToIns404() {
            assertDomainEnvelope(
                    new InstrumentNotFoundException("ACME"),
                    "INS-404", HttpStatus.NOT_FOUND, "Instrument not found");
        }

        @Test
        @DisplayName("Insufficient funds maps to ORD-400 with status 400")
        void insufficientFunds_mapsToOrd400() {
            assertDomainEnvelope(
                    new InsufficientFundsException(7L, new BigDecimal("100.00"), new BigDecimal("50.00")),
                    "ORD-400", HttpStatus.BAD_REQUEST, "Insufficient funds");
        }

        @Test
        @DisplayName("Reused idempotency key maps to ORD-409 with status 409")
        void reusedIdempotencyKey_mapsToOrd409() {
            assertDomainEnvelope(
                    new DuplicateOrderException("6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e"),
                    "ORD-409", HttpStatus.CONFLICT, "Duplicate order");
        }

        @Test
        @DisplayName("Invalid input maps to VAL-422 with status 422")
        void invalidInput_mapsToVal422() {
            assertDomainEnvelope(
                    new InvalidOrderException("quantity", 0),
                    "VAL-422", HttpStatus.UNPROCESSABLE_ENTITY, "Invalid input");
        }

        @Test
        @DisplayName("A bean-validation failure also maps to VAL-422 with status 422")
        void beanValidationFailure_mapsToVal422() throws NoSuchMethodException {
            ResponseEntity<ErrorResponse> response = handler.handleValidation(validationException());

            assertEquals(HttpStatus.UNPROCESSABLE_ENTITY, response.getStatusCode());
            assertErrorCode(response, "VAL-422");
            assertMessage(response, "Invalid input");
        }

        @Test
        @DisplayName("A missing or invalid token maps to AUTH-401 with status 401")
        void invalidToken_mapsToAuth401() {
            assertDomainEnvelope(
                    new AuthenticationException("malformed token"),
                    "AUTH-401", HttpStatus.UNAUTHORIZED, "Unauthorised");
        }
    }

    @Nested
    @DisplayName("Clients branch on the code, never on the status or the message")
    class BranchabilityTests {

        @Test
        @DisplayName("ACC-404 and INS-404 share status 404 yet carry different codes")
        void theTwo404CodesShareAStatusButDiffer() {
            assertEquals(HttpStatus.NOT_FOUND, ErrorCatalogue.statusFor("ACC-404"));
            assertEquals(HttpStatus.NOT_FOUND, ErrorCatalogue.statusFor("INS-404"));

            assertTrue(ErrorCatalogue.asMap().containsKey("ACC-404"));
            assertTrue(ErrorCatalogue.asMap().containsKey("INS-404"));
        }

        @Test
        @DisplayName("Two different failures carry the same ORD-409 code but different messages")
        void ord409CarriesDifferentMessages() {
            assertDomainEnvelope(
                    new InsufficientHoldingsException(7L, "ACME", new BigDecimal("10"), new BigDecimal("5")),
                    "ORD-409", HttpStatus.CONFLICT, "Insufficient holdings");

            assertDomainEnvelope(
                    new DuplicateOrderException("some-key-0001"),
                    "ORD-409", HttpStatus.CONFLICT, "Duplicate order");
        }

        @Test
        @DisplayName("The message never leaks an internal identifier into the body")
        void messageNeverLeaksInternalDetail() {
            ResponseEntity<ErrorResponse> response = handler.handleDomainException(
                    new InsufficientFundsException(7L, new BigDecimal("100.00"), new BigDecimal("50.00")));

            assertMessage(response, "Insufficient funds");
            assertFalse(response.getBody().getMessage().contains("7"),
                    "message must not carry the account key");
            assertFalse(response.getBody().getMessage().contains("100.00"),
                    "message must not carry internal amounts");
        }

        @Test
        @DisplayName("The envelope carries exactly the two contract fields and nothing else")
        void envelopeHasExactlyTwoFields() {
            Set<String> names = Arrays.stream(ErrorResponse.class.getDeclaredFields())
                    .map(Field::getName)
                    .collect(Collectors.toSet());

            assertEquals(2, names.size(), "envelope must have exactly two fields");
            assertTrue(names.contains("errorCode"));
            assertTrue(names.contains("message"));
        }
    }

    private void assertDomainEnvelope(DomainException exception, String expectedCode,
                                      HttpStatus expectedStatus, String expectedMessage) {
        ResponseEntity<ErrorResponse> response = handler.handleDomainException(exception);

        assertEquals(expectedStatus, response.getStatusCode(), "status");
        assertErrorCode(response, expectedCode);
        assertMessage(response, expectedMessage);
    }

    private void assertErrorCode(ResponseEntity<ErrorResponse> response, String expected) {
        assertNotNull(response.getBody());
        assertEquals(expected, response.getBody().getErrorCode());
    }

    private void assertMessage(ResponseEntity<ErrorResponse> response, String expected) {
        assertNotNull(response.getBody());
        assertEquals(expected, response.getBody().getMessage());
    }

    private MethodArgumentNotValidException validationException() throws NoSuchMethodException {
        MethodParameter parameter = new MethodParameter(
                SampleController.class.getMethod("placeOrder", PlaceOrderRequest.class), 0);
        BindingResult binding = new BeanPropertyBindingResult(new PlaceOrderRequest(), "request");
        binding.rejectValue("quantity", "Min", "quantity must be at least 1");
        return new MethodArgumentNotValidException(parameter, binding);
    }

    @SuppressWarnings("unused")
    private static class SampleController {
        public void placeOrder(PlaceOrderRequest request) {
        }
    }
}