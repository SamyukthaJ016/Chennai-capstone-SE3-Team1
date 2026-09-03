package com.team1.trading.domain.exception;

/**
 * Rules 4 and 5, VAL-422: a quantity or a price that is not greater than zero.
 *
 * The DTO carries the same constraints as Bean Validation annotations, but an
 * annotation only fires when somebody runs a validator, and the domain has to
 * hold for a caller that never ran one. That is why these two are checked
 * twice, and this is what the second check throws.
 */
public class InvalidOrderException extends com.team1.trading.domain.exception.DomainException {

    public static final String CODE = "VAL-422";
    public static final String MESSAGE = "Invalid input";

    private final String field;
    private final Object rejectedValue;

    public InvalidOrderException(String field, Object rejectedValue) {
        super(CODE, MESSAGE);
        this.field = field;
        this.rejectedValue = rejectedValue;
    }

    /** Which field failed. For the server log. */
    public String getField() {
        return field;
    }

    /** What was submitted. For the server log, never for the body. */
    public Object getRejectedValue() {
        return rejectedValue;
    }
}
