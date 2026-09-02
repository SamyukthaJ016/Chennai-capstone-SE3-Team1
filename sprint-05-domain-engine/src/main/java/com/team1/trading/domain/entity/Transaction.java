package com.team1.trading.domain.entity;

import java.time.LocalDateTime;
import java.util.Objects;

/** Common shape shared by TransactionSuccess and TransactionFailure. */
public abstract class Transaction {

    private final Long transactionId;
    private final Long orderId;
    private final LocalDateTime transactionTimestamp;

    protected Transaction(Long transactionId, Long orderId) {
        this.transactionId = transactionId;
        this.orderId = Objects.requireNonNull(orderId, "orderId must not be null");
        this.transactionTimestamp = LocalDateTime.now();
    }

    public Long getTransactionId() {
        return transactionId;
    }

    public Long getOrderId() {
        return orderId;
    }

    public LocalDateTime getTransactionTimestamp() {
        return transactionTimestamp;
    }
}