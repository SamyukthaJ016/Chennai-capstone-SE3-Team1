package com.team1.trading.api.dto;

import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * One entry of {@code GET /api/v1/accounts/{id}/orders}, as fixed by contracts/trade-api.yaml.
 * The audit trail: every order recorded against the account, including rejected and cancelled
 * ones, newest first.
 */
public class OrderHistoryEntry {

    private String orderId;
    private Long accountId;
    private String symbol;
    private OrderSide side;
    private Integer quantity;
    private BigDecimal price;
    private BigDecimal executedPrice;
    private OrderStatus status;
    private String idempotencyKey;
    private LocalDateTime createdOn;

    public OrderHistoryEntry() {
    }

    public OrderHistoryEntry(String orderId, Long accountId, String symbol, OrderSide side,
                             Integer quantity, BigDecimal price, BigDecimal executedPrice,
                             OrderStatus status, String idempotencyKey, LocalDateTime createdOn) {
        this.orderId = orderId;
        this.accountId = accountId;
        this.symbol = symbol;
        this.side = side;
        this.quantity = quantity;
        this.price = price;
        this.executedPrice = executedPrice;
        this.status = status;
        this.idempotencyKey = idempotencyKey;
        this.createdOn = createdOn;
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public Long getAccountId() {
        return accountId;
    }

    public void setAccountId(Long accountId) {
        this.accountId = accountId;
    }

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
    }

    public OrderSide getSide() {
        return side;
    }

    public void setSide(OrderSide side) {
        this.side = side;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    public BigDecimal getExecutedPrice() {
        return executedPrice;
    }

    public void setExecutedPrice(BigDecimal executedPrice) {
        this.executedPrice = executedPrice;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public void setIdempotencyKey(String idempotencyKey) {
        this.idempotencyKey = idempotencyKey;
    }

    public LocalDateTime getCreatedOn() {
        return createdOn;
    }

    public void setCreatedOn(LocalDateTime createdOn) {
        this.createdOn = createdOn;
    }
}