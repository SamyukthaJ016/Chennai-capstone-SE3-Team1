package com.team1.trading.domain.entity;

import java.math.BigDecimal;

public class TransactionFailure extends Transaction {

    private final String errorId;
    private final BigDecimal value;
    private final String reasonForFailure;

    public TransactionFailure(Long transactionId, Long orderId, String errorId,
                              BigDecimal value, String reasonForFailure) {
        super(transactionId, orderId);
        this.errorId = errorId;
        this.value = value;
        this.reasonForFailure = reasonForFailure;
    }

    public String getErrorId() {
        return errorId;
    }

    public BigDecimal getValue() {
        return value;
    }

    public String getReasonForFailure() {
        return reasonForFailure;
    }

    // retry() and logFailure() intentionally left out - same reason as
    // TransactionSuccess: need the actual behaviour defined first.

}