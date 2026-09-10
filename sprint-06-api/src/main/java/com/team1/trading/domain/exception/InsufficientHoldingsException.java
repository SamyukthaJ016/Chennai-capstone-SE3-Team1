package com.team1.trading.domain.exception;

import java.math.BigDecimal;

public class InsufficientHoldingsException extends DomainException {

    public static final String CODE = "ORD-409";
    public static final String MESSAGE = "Insufficient holdings";

    private final Long accountId;
    private final String symbol;
    private final BigDecimal requested;
    private final BigDecimal held;

    public InsufficientHoldingsException(Long accountId, String symbol,
                                         BigDecimal requested, BigDecimal held) {
        super(CODE, MESSAGE);
        this.accountId = accountId;
        this.symbol = symbol;
        this.requested = requested;
        this.held = held;
    }

    public Long getAccountId() {
        return accountId;
    }

    public String getSymbol() {
        return symbol;
    }

    public BigDecimal getRequested() {
        return requested;
    }

    public BigDecimal getHeld() {
        return held;
    }
}
