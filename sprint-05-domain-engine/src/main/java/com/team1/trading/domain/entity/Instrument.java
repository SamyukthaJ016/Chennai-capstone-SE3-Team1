package com.team1.trading.domain.entity;

import java.time.LocalDateTime;

/**
 * A tradable instrument. active/deactivate toggles whether it's currently
 * tradable;
 */
public class Instrument {

    private Long instrumentId;
    private String instrumentName;
    private boolean active;
    private LocalDateTime updatedOn;

    /** For a new instrument not yet persisted - no id assigned. */
    public Instrument(String instrumentName) {
        this.instrumentName = instrumentName;
        this.active = true;
        this.updatedOn = null;
    }

    /** For reconstructing an instrument already in storage. */
    public Instrument(Long instrumentId, String instrumentName, boolean active, LocalDateTime deletedOn) {
        this.instrumentId = instrumentId;
        this.instrumentName = instrumentName;
        this.active = active;
        this.updatedOn = deletedOn;
    }

    public Long getInstrumentId() {
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