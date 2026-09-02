package com.team1.trading.domain.exception;

import java.math.BigDecimal;

/** Rule 6, ORD-400: a buy costs more than the available wallet balance. */
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

    /** Quantity multiplied by price. For the server log. */
    public BigDecimal getRequired() {
        return required;
    }

    /** The balance when the rule ran. For the server log, never for the body. */
    public BigDecimal getAvailable() {
        return available;
    }
}
