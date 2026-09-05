package com.team1.trading.domain.entity;

import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.entity.types.OrderType;
import com.team1.trading.domain.entity.types.OrderSide;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;

public class Order {

    private Long orderId;
    private Long clientId;
    private Long accountId;
    private String instrumentId;
    private OrderType orderType;
    private OrderSide side;
    private BigDecimal quantity;
    private BigDecimal price;
    private BigDecimal executedPrice;
    private OrderStatus status;
    private String idempotencyKey;
    private String externalOrderId;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Order(Long clientId, Long accountId, String instrumentId, OrderType orderType,
                 OrderSide side, BigDecimal quantity, BigDecimal price, String idempotencyKey) {
        this.clientId = Objects.requireNonNull(clientId, "userId must not be null");
        this.accountId = Objects.requireNonNull(accountId, "accountId must not be null");
        this.instrumentId = Objects.requireNonNull(instrumentId, "instrumentId must not be null");
        this.orderType = Objects.requireNonNull(orderType, "orderType must not be null");
        this.side = Objects.requireNonNull(side, "side must not be null");
        if (quantity == null || quantity.signum() <= 0) throw new IllegalArgumentException("quantity must be greater than zero");
        this.quantity = quantity;
        this.price = price;
        this.idempotencyKey = idempotencyKey;
        this.status = OrderStatus.NEW;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = this.createdAt;
    }

    public Long getOrderId() { return orderId; }
    public Long getClientId() { return clientId; }
    public Long getAccountId() { return accountId; }
    public String getInstrumentId() { return instrumentId; }
    public OrderType getOrderType() { return orderType; }
    public OrderSide getSide() { return side; }
    public BigDecimal getQuantity() { return quantity; }
    public BigDecimal getPrice() { return price; }
    public BigDecimal getExecutedPrice() { return executedPrice; }
    public OrderStatus getStatus() { return status; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public String getExternalOrderId() { return externalOrderId; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }

    public void markInProgress() {
        requireTransitionableFromNew();
        this.status = OrderStatus.NEW;
        this.updatedAt = LocalDateTime.now();
    }

    /** Filled by the Trade Executor against a live quote; that quote is the executed price. */
    public void markCompleted(BigDecimal executedPrice) {
        requireTransitionableFromNew();
        this.executedPrice = Objects.requireNonNull(executedPrice, "executedPrice must not be null");
        this.status = OrderStatus.FILLED;
        this.updatedAt = LocalDateTime.now();
    }

    public void markFailed() {
        requireTransitionableFromNew();
        this.status = OrderStatus.REJECTED;
        this.updatedAt = LocalDateTime.now();
    }

    public void cancel() {
        requireTransitionableFromNew();
        this.status = OrderStatus.CANCELLED;
        this.updatedAt = LocalDateTime.now();
    }

    /** NEW is the only non-terminal state; every terminal state refuses to move again. */
    private void requireTransitionableFromNew() {
        if (this.status != OrderStatus.NEW) {
            throw new IllegalStateException("order " + orderId + " is " + status + ", cannot transition");
        }
    }

}
