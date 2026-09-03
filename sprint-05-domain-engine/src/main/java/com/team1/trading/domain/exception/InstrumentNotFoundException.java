package com.team1.trading.domain.exception;

/**
 * Rule 3, INS-404: the symbol is unknown, or it is known and no longer
 * tradable. Both answer identically, so order placement cannot be used to
 * enumerate which symbols exist.
 */
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
