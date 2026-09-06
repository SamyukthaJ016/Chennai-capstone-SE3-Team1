package com.team1.trading.domain.entity;

import java.time.LocalDateTime;

public class Instrument {

    private String instrumentId;
    private String instrumentName;
    private boolean active;
    private LocalDateTime updatedOn;

    public Instrument(String instrumentId, String instrumentName) {
        this.instrumentId = instrumentId;
        this.instrumentName = instrumentName;
        this.active = true;
        this.updatedOn = null;
    }

    public Instrument(String instrumentId, String instrumentName, boolean active, LocalDateTime deletedOn) {
        this.instrumentId = instrumentId;
        this.instrumentName = instrumentName;
        this.active = active;
        this.updatedOn = deletedOn;
    }

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

    public boolean isTradable() {
        return active && updatedOn == null;
    }

    public void update() {
        this.updatedOn = LocalDateTime.now();
        this.active = false;
    }
}
