package com.team1.trading.domain.exception;

public class OrderConflictException extends DomainException {

    public static final String CODE = "ORD-409";
    public static final String MESSAGE = "Order rejected";

    private final String reason;

    public OrderConflictException(String reason) {
        super(CODE, MESSAGE);
        this.reason = reason;
    }

    public String getReason() {
        return reason;
    }
}