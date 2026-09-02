package com.team1.trading.domain.entity;

import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.entity.types.OrderType;
import com.team1.trading.domain.entity.types.TransactionType;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.UUID;

public class Order {

    private Long orderId;
    private UUID clientId;
    private Long instrumentId;
    private OrderType orderType;
    private TransactionType transactionType;
    private int quantity;
    private boolean scheduled;
    private BigDecimal targetPrice; // Null for standard market orders, set for scheduled orders
    private String exchange;
    private OrderStatus status;
    private LocalDateTime orderTimestamp;
    private String idempotencyKey;

    public Order(UUID clientId, Long instrumentId, OrderType orderType, TransactionType transactionType,
                 int quantity, boolean scheduled, BigDecimal targetPrice, String exchange, String idempotencyKey) {
        this.clientId = Objects.requireNonNull(clientId, "clientId must not be null");
        this.instrumentId = Objects.requireNonNull(instrumentId, "instrumentId must not be null");
        this.orderType = Objects.requireNonNull(orderType, "orderType must not be null");
        this.transactionType = Objects.requireNonNull(transactionType, "transactionType must not be null");
        if (quantity <= 0) throw new IllegalArgumentException("quantity must be greater than zero");
        this.quantity = quantity;
        this.scheduled = scheduled;
        this.targetPrice = targetPrice;
        this.exchange = exchange;
        this.idempotencyKey = idempotencyKey;
        this.status = OrderStatus.NEW;
        this.orderTimestamp = LocalDateTime.now();
    }

    public Long getOrderId() { return orderId; }
    public UUID getClientId() { return clientId; }
    public Long getInstrumentId() { return instrumentId; }
    public OrderType getOrderType() { return orderType; }
    public TransactionType getTransactionType() { return transactionType; }
    public int getQuantity() { return quantity; }
    public boolean isScheduled() { return scheduled; }
    public BigDecimal getTargetPrice() { return targetPrice; }
    public String getExchange() { return exchange; }
    public OrderStatus getStatus() { return status; }
    public LocalDateTime getOrderTimestamp() { return orderTimestamp; }
    public String getIdempotencyKey() { return idempotencyKey; }

    public void markInProgress() {
        this.status = OrderStatus.IN_PROGRESS;
    }

    public void markCompleted() {
        this.status = OrderStatus.COMPLETED;
    }

    public void markFailed() {
        this.status = OrderStatus.FAILED;
    }

    public void cancel() {
        this.status = OrderStatus.CANCELLED;
    }

}