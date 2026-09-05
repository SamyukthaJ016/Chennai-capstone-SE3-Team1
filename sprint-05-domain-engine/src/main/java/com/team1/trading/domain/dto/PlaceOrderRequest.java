package com.team1.trading.domain.dto;
import com.team1.trading.domain.entity.types.OrderSide;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public class PlaceOrderRequest {

    @NotNull(message = "accountId must not be null")
    @Min(value = 1, message = "accountId must be at least 1")
    private Long accountId;

    @NotBlank(message = "symbol must not be blank")
    @Size(min = 1, max = 20, message = "symbol length must be between 1 and 20 characters")
    private String symbol;

    @NotNull(message = "side must not be null")
    private OrderSide side;

    @NotNull(message = "quantity must not be null")
    @Min(value = 1, message = "quantity must be at least 1")
    private Integer quantity;

    @NotNull(message = "price must not be null")
    @DecimalMin(value = "0.01", message = "price must be greater than zero")
    @Digits(integer = 12, fraction = 2, message = "price must have at most 2 decimal places")
    private BigDecimal price;

    @NotBlank(message = "idempotencyKey must not be blank")
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