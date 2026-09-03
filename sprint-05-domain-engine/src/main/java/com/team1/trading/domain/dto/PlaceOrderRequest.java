package com.team1.trading.domain.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

/**
 * Request body for POST /api/v1/orders.
 *
 * Modeled exactly on components.schemas.PlaceOrderRequest in contracts/trade-api.yaml.
 * That schema is binding — every constraint here traces back to a line in the contract,
 * and nothing here adds a constraint the contract doesn't specify.
 *
 * additionalProperties: false in the schema is enforced via @JsonIgnoreProperties(ignoreUnknown = false)
 * below, since Bean Validation field annotations cannot express "reject unknown JSON fields" —
 * that check happens at deserialization time, not at field-validation time.
 */
@JsonIgnoreProperties(ignoreUnknown = false)
public class PlaceOrderRequest {

    // contract: type: integer, format: int64, minimum: 1, required
    @NotNull(message = "accountId must not be null")
    @Min(value = 1, message = "accountId must be at least 1")
    private Long accountId;

    // contract: type: string, minLength: 1, maxLength: 20, required
    // Note: contract's minLength: 1 permits a whitespace-only string of length 1; we use
    // @Size(min = 1) rather than @NotBlank to match the contract literally rather than
    // silently tightening it. If blank symbols should be rejected as a business rule,
    // that belongs in the service layer, not smuggled into contract-level validation here.
    @NotNull(message = "symbol must not be null")
    @Size(min = 1, max = 20, message = "symbol length must be between 1 and 20 characters")
    private String symbol;

    // contract: OrderSide enum [BUY, SELL], required
    @NotNull(message = "side must not be null")
    private OrderSide side;

    // contract: type: integer, format: int32, minimum: 1, required
    @NotNull(message = "quantity must not be null")
    @Min(value = 1, message = "quantity must be at least 1")
    private Integer quantity;

    // contract: type: number, format: double, exclusiveMinimum: 0, multipleOf: 0.01, required
    // Held as BigDecimal per the contract's explicit instruction never to use double for money.
    // @DecimalMin(0.01, inclusive = false) expresses "strictly greater than zero" without
    // hardcoding a floor value, so it tracks exclusiveMinimum: 0 directly rather than
    // coincidentally landing on the right number via the cent granularity.
    // @Digits(fraction = 2) enforces multipleOf: 0.01 (at most 2 decimal places); the
    // integer digit count is left unbounded since the contract sets no upper limit on price.
    @NotNull(message = "price must not be null")
    @DecimalMin(value = "0.0", inclusive = false, message = "price must be greater than zero")
    @Digits(integer = Integer.MAX_VALUE, fraction = 2, message = "price must have at most 2 decimal places")
    private BigDecimal price;

    // contract: type: string, minLength: 8, maxLength: 100, required
    @NotNull(message = "idempotencyKey must not be null")
    @Size(min = 8, max = 100, message = "idempotencyKey length must be between 8 and 100 characters")
    private String idempotencyKey;

    public PlaceOrderRequest() {
    }

    public PlaceOrderRequest(Long accountId, String symbol, OrderSide side, Integer quantity, BigDecimal price, String idempotencyKey) {
        this.accountId = accountId;
        this.symbol = symbol;
        this.side = side;
        this.quantity = quantity;
        this.price = price;
        this.idempotencyKey = idempotencyKey;
    }

    public Long getAccountId() { return accountId; }
    public void setAccountId(Long accountId) { this.accountId = accountId; }

    public String getSymbol() { return symbol; }
    public void setSymbol(String symbol) { this.symbol = symbol; }

    public OrderSide getSide() { return side; }
    public void setSide(OrderSide side) { this.side = side; }

    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) { this.quantity = quantity; }

    public BigDecimal getPrice() { return price; }
    public void setPrice(BigDecimal price) { this.price = price; }

    public String getIdempotencyKey() { return idempotencyKey; }
    public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
}