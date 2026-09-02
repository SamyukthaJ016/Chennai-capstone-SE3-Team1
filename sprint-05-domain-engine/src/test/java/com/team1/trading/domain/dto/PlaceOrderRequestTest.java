package com.team1.trading.domain.dto;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PlaceOrderRequestTest {

    private static Validator validator;

    @BeforeAll
    static void setUpValidator() {
        ValidatorFactory factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    private PlaceOrderRequest createValidRequest() {
        return new PlaceOrderRequest(
                1L,
                "ACME",
                OrderSide.BUY,
                100,
                new BigDecimal("25.50"),
                "6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e"
        );
    }

    @Test
    @DisplayName("Valid request passes validation")
    void validRequest_passesValidation() {
        PlaceOrderRequest request = createValidRequest();
        Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
        assertTrue(violations.isEmpty(), "Valid request should produce zero violations");
    }

    @Nested
    @DisplayName("Null Required Field Tests")
    class NullFieldTests {

        @Test
        @DisplayName("Null accountId is rejected")
        void nullAccountId_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setAccountId(null);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("accountId")));
        }

        @Test
        @DisplayName("Null symbol is rejected")
        void nullSymbol_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setSymbol(null);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("symbol")));
        }

        @Test
        @DisplayName("Null side is rejected")
        void nullSide_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setSide(null);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("side")));
        }

        @Test
        @DisplayName("Null quantity is rejected")
        void nullQuantity_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setQuantity(null);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("quantity")));
        }

        @Test
        @DisplayName("Null price is rejected")
        void nullPrice_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setPrice(null);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("price")));
        }

        @Test
        @DisplayName("Null idempotencyKey is rejected")
        void nullIdempotencyKey_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setIdempotencyKey(null);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("idempotencyKey")));
        }
    }

    @Nested
    @DisplayName("Boundary Checks: accountId")
    class AccountIdBoundaryTests {

        @Test
        @DisplayName("accountId = 0 (one step below minimum 1) is rejected")
        void accountId_zero_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setAccountId(0L);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("accountId")));
        }

        @Test
        @DisplayName("accountId = 1 (exact minimum limit) passes")
        void accountId_one_passes() {
            PlaceOrderRequest request = createValidRequest();
            request.setAccountId(1L);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.isEmpty());
        }
    }

    @Nested
    @DisplayName("Boundary Checks: symbol")
    class SymbolBoundaryTests {

        @Test
        @DisplayName("symbol length = 0 (empty string) is rejected")
        void symbol_empty_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setSymbol("");

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("symbol")));
        }

        @Test
        @DisplayName("symbol length = 1 (minimum limit) passes")
        void symbol_length1_passes() {
            PlaceOrderRequest request = createValidRequest();
            request.setSymbol("A");

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.isEmpty());
        }

        @Test
        @DisplayName("symbol length = 20 (maximum limit) passes")
        void symbol_length20_passes() {
            PlaceOrderRequest request = createValidRequest();
            request.setSymbol("A".repeat(20));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.isEmpty());
        }

        @Test
        @DisplayName("symbol length = 21 (one step over limit) is rejected")
        void symbol_length21_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setSymbol("A".repeat(21));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("symbol")));
        }
    }

    @Nested
    @DisplayName("Boundary Checks: quantity")
    class QuantityBoundaryTests {

        @Test
        @DisplayName("quantity = -1 is rejected")
        void quantity_negative_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setQuantity(-1);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("quantity")));
        }

        @Test
        @DisplayName("quantity = 0 (non-positive boundary) is rejected")
        void quantity_zero_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setQuantity(0);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("quantity")));
        }

        @Test
        @DisplayName("quantity = 1 (minimum limit) passes")
        void quantity_one_passes() {
            PlaceOrderRequest request = createValidRequest();
            request.setQuantity(1);

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.isEmpty());
        }
    }

    @Nested
    @DisplayName("Boundary Checks: price")
    class PriceBoundaryTests {

        @Test
        @DisplayName("price = -0.01 is rejected")
        void price_negative_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setPrice(new BigDecimal("-0.01"));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("price")));
        }

        @Test
        @DisplayName("price = 0.00 (non-positive boundary) is rejected")
        void price_zero_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setPrice(new BigDecimal("0.00"));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("price")));
        }

        @Test
        @DisplayName("price = 0.01 (minimum limit) passes")
        void price_minimumAllowed_passes() {
            PlaceOrderRequest request = createValidRequest();
            request.setPrice(new BigDecimal("0.01"));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.isEmpty());
        }

        @Test
        @DisplayName("price with 3 decimal places is rejected")
        void price_moreThanTwoDecimals_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setPrice(new BigDecimal("25.505"));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("price")));
        }
    }

    @Nested
    @DisplayName("Boundary Checks: idempotencyKey")
    class IdempotencyKeyBoundaryTests {

        @Test
        @DisplayName("idempotencyKey length = 7 (one step below limit) is rejected")
        void idempotencyKey_length7_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setIdempotencyKey("1234567");

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("idempotencyKey")));
        }

        @Test
        @DisplayName("idempotencyKey length = 8 (minimum limit) passes")
        void idempotencyKey_length8_passes() {
            PlaceOrderRequest request = createValidRequest();
            request.setIdempotencyKey("12345678");

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.isEmpty());
        }

        @Test
        @DisplayName("idempotencyKey length = 100 (maximum limit) passes")
        void idempotencyKey_length100_passes() {
            PlaceOrderRequest request = createValidRequest();
            request.setIdempotencyKey("K".repeat(100));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertTrue(violations.isEmpty());
        }

        @Test
        @DisplayName("idempotencyKey length = 101 (one step over limit) is rejected")
        void idempotencyKey_length101_isRejected() {
            PlaceOrderRequest request = createValidRequest();
            request.setIdempotencyKey("K".repeat(101));

            Set<ConstraintViolation<PlaceOrderRequest>> violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertTrue(violations.stream().anyMatch(v -> v.getPropertyPath().toString().equals("idempotencyKey")));
        }
    }
}