package com.team1.trading.domain.exception;

public class InstrumentNotFoundException extends DomainException {

    public static final String CODE = "INS-404";
    public static final String MESSAGE = "Instrument not found";

    private final String symbol;

    public InstrumentNotFoundException(String symbol) {
        super(CODE, MESSAGE);
        this.symbol = symbol;
    }

    public String getSymbol() {
        return symbol;
    }
}
