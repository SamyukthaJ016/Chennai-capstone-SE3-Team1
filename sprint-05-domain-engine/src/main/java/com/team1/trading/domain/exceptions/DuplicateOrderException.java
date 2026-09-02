package com.team1.trading.domain.exception;

/**
 * Rule 8, ORD-409: the idempotency key has already been accepted.
 *
 * Raised when the atomic claim on the key loses, never after a read that found
 * it: two concurrent requests carrying one key both pass a read-then-write
 * check, and losing that race duplicates a trade.
 */
public class DuplicateOrderException extends DomainException {

    public static final String CODE = "ORD-409";
    public static final String MESSAGE = "Duplicate order";

    private final String idempotencyKey;

    public DuplicateOrderException(String idempotencyKey) {
        super(CODE, MESSAGE);
        this.idempotencyKey = idempotencyKey;
    }

    /** For the server log, so the first acceptance can be found. */
    public String getIdempotencyKey() {
        return idempotencyKey;
    }
}
