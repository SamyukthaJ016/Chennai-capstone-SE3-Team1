package com.team1.trading.domain.exception;

/**
 * The one type a caller catches in one place and maps.
 *
 * It carries the catalogue code and not an HTTP status, so the same code can
 * become a status in one layer and a rejection reason in another. One code can
 * mean two things: ORD-409 is both insufficient holdings and a duplicate order.
 */
public abstract class DomainException extends RuntimeException {

    private final String code;

    protected DomainException(String code, String message) {
        super(message);
        this.code = code;
    }

    /** The catalogue code: ACC-404, ACC-403, INS-404, VAL-422, ORD-400, ORD-409. */
    public String getCode() {
        return code;
    }
}
