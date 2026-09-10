package com.team1.trading.domain.exception;

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

    public String getField() {
        return field;
    }

    public Object getRejectedValue() {
        return rejectedValue;
    }
}
