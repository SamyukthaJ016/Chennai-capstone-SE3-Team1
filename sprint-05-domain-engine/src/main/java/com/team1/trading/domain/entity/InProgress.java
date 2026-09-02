package com.team1.trading.domain.entity;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.Objects;

public class InProgress {

    private Long progressId;
    private final Order order;
    private final Long instrumentId;
    private final int quantity;
    private final BigDecimal targetPrice; // Retained from order for fast evaluation
    private final LocalDateTime enteredTimestamp;
    private LocalDateTime resolvedTimestamp;

    public InProgress(Long progressId, Order order) {
        this.progressId = progressId;
        this.order = Objects.requireNonNull(order, "order must not be null");
        this.instrumentId = order.getInstrumentId();
        this.quantity = order.getQuantity();
        this.targetPrice = order.getTargetPrice();
        this.enteredTimestamp = LocalDateTime.now();

        // Mutate order state to IN_PROGRESS upon creation
        this.order.markInProgress();
    }

    public Long getProgressId() { return progressId; }
    public Order getOrder() { return order; }
    public Long getInstrumentId() { return instrumentId; }
    public int getQuantity() { return quantity; }
    public BigDecimal getTargetPrice() { return targetPrice; }
    public LocalDateTime getEnteredTimestamp() { return enteredTimestamp; }
    public LocalDateTime getResolvedTimestamp() { return resolvedTimestamp; }

    /**
     * Evaluates whether a market condition satisfies execution criteria.
     *
     * For scheduled buys (Order.isScheduled() == true):
     * - Current market price must be LESS THAN OR EQUAL TO targetPrice.
     * - Available market depth must be GREATER THAN OR EQUAL TO order quantity.
     *
     * For non-scheduled immediate orders:
     * - Quantity must be available in market depth.
     */
    public boolean matchesExecutionCondition(BigDecimal currentMarketPrice, int availableQuantity) {
        if (availableQuantity < this.quantity) {
            return false;
        }

        if (order.isScheduled()) {
            if (targetPrice == null) {
                throw new IllegalStateException("Scheduled order must have a target price");
            }
            BigDecimal normalizedMarketPrice = currentMarketPrice;
            // Scheduled BUY triggers when market price drops to or below target price
            return normalizedMarketPrice.compareTo(targetPrice) <= 0;
        }

        return true;
    }

    /**
     * Completes the in-progress tracking and creates a TransactionSuccess record.
     */
    public TransactionSuccess markCompleted(Long transactionId, BigDecimal executionPrice) {
        this.order.markCompleted();
        this.resolvedTimestamp = LocalDateTime.now();
        return new TransactionSuccess(
                transactionId,
                order.getOrderId(),
                BigDecimal.valueOf(quantity).setScale(2, RoundingMode.UNNECESSARY),
                executionPrice
        );
    }

    /**
     * Fails the in-progress tracking and creates a TransactionFailure record.
     */
    public TransactionFailure markFailed(Long transactionId, String errorId, BigDecimal attemptValue, String reason) {
        this.order.markFailed();
        this.resolvedTimestamp = LocalDateTime.now();
        return new TransactionFailure(
                transactionId,
                order.getOrderId(),
                errorId,
                attemptValue,
                reason
        );
    }

    }