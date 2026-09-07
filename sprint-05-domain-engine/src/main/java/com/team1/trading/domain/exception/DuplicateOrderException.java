package com.team1.trading.domain.exception;

public class DuplicateOrderException extends DomainException {

    public static final String CODE = "ORD-409";
    public static final String MESSAGE = "Duplicate order";

    private final String idempotencyKey;

    public DuplicateOrderException(String idempotencyKey) {
        super(CODE, MESSAGE);
        this.idempotencyKey = idempotencyKey;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }
}
