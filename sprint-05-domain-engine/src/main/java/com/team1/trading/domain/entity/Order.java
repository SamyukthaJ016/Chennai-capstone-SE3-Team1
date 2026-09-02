package com.team1.trading.domain.entity;

import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.entity.types.OrderType;
import com.team1.trading.domain.entity.types.TransactionType;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;

public class Order {

    private Long orderId;
    private Long userId;
    private Long accountId;
    private String instrumentId;
    private OrderType orderType;
    private TransactionType side;
    private BigDecimal quantity;
    private BigDecimal price;
    private OrderStatus status;
    private String idempotencyKey;
    private String externalOrderId;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Order(Long userId, Long accountId, String instrumentId, OrderType orderType,
                 TransactionType side, BigDecimal quantity, BigDecimal price, String idempotencyKey) {
        this.userId = Objects.requireNonNull(userId, "userId must not be null");
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
    public Long getUserId() { return userId; }
    public Long getAccountId() { return accountId; }
    public String getInstrumentId() { return instrumentId; }
    public OrderType getOrderType() { return orderType; }
    public TransactionType getSide() { return side; }
    public BigDecimal getQuantity() { return quantity; }
    public BigDecimal getPrice() { return price; }
    public OrderStatus getStatus() { return status; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public String getExternalOrderId() { return externalOrderId; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }

    public void markInProgress() {
        this.status = OrderStatus.IN_PROGRESS;
        this.updatedAt = LocalDateTime.now();
    }

    public void markCompleted() {
        this.status = OrderStatus.COMPLETED;
        this.updatedAt = LocalDateTime.now();
    }

    public void markFailed() {
        this.status = OrderStatus.FAILED;
        this.updatedAt = LocalDateTime.now();
    }

    public void cancel() {
        this.status = OrderStatus.CANCELLED;
        this.updatedAt = LocalDateTime.now();
    }

}
