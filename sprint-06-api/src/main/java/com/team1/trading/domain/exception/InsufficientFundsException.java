package com.team1.trading.domain.exception;

import java.math.BigDecimal;

public class InsufficientFundsException extends DomainException {

    public static final String CODE = "ORD-400";
    public static final String MESSAGE = "Insufficient funds";

    private final Long accountId;
    private final BigDecimal required;
    private final BigDecimal available;

    public InsufficientFundsException(Long accountId, BigDecimal required, BigDecimal available) {
        super(CODE, MESSAGE);
        this.accountId = accountId;
        this.required = required;
        this.available = available;
    }

    public Long getAccountId() {
        return accountId;
    }

    public BigDecimal getRequired() {
        return required;
    }

    public BigDecimal getAvailable() {
        return available;
    }
}
