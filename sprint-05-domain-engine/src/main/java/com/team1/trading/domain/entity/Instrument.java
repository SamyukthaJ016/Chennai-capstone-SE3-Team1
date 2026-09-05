package com.team1.trading.domain.entity;

import java.time.LocalDateTime;

/**
 * A tradable instrument. active/close toggles whether it's currently
 * tradable;
 *
 * The symbol is the key. orders.instrument_id is VARCHAR(50) and holds the
 * symbol itself, which is also what PlaceOrderRequest.symbol carries, so one
 * instrument has one identity from the request through to the order row.
 */
public class Instrument {

    private String instrumentId;
    private String instrumentName;
    private boolean active;
    private LocalDateTime updatedOn;

    /** For a new instrument not yet persisted. */
    public Instrument(String instrumentId, String instrumentName) {
        this.instrumentId = instrumentId;
        this.instrumentName = instrumentName;
        this.active = true;
        this.updatedOn = null;
    }

    /** For reconstructing an instrument already in storage. */
    public Instrument(String instrumentId, String instrumentName, boolean active, LocalDateTime deletedOn) {
        this.instrumentId = instrumentId;
        this.instrumentName = instrumentName;
        this.active = active;
        this.updatedOn = deletedOn;
    }

    /** The symbol, as it appears on every order. */
    public String getInstrumentId() {
        return instrumentId;
    }

    public String getInstrumentName() {
        return instrumentName;
    }

    public boolean isActive() {
        return active;
    }

    public LocalDateTime getUpdatedOn() {
        return updatedOn;
    }

    public void activate() {
        this.active = true;
    }

    public void deactivate() {
        this.active = false;
    }

    /** Tradable only while active and not soft-deleted. */
    public boolean isTradable() {
        return active && updatedOn == null;
    }

    public void update() {
        this.updatedOn = LocalDateTime.now();
        this.active = false;
    }
}
