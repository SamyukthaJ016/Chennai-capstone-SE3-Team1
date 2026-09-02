package com.team1.trading.domain.entity;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.UUID;

/**
 * Common shape shared by PortfolioHolding and PortfolioPosition: a
 * client's stake in one instrument, tracked by quantity, average price
 * paid, and gains against the current market price.
 */
public abstract class PortfolioEntry {

    private final Long id;
    private final UUID clientId;
    private final Long instrumentId;
    private int quantity;
    private BigDecimal pricePerUnit;
    private BigDecimal overallGains;
    private final LocalDateTime createdAt;
    private LocalDateTime updatedAt;


    protected PortfolioEntry(Long id, UUID clientId, Long instrumentId, int quantity, BigDecimal pricePerUnit) {
        this.id = id;
        this.clientId = Objects.requireNonNull(clientId, "clientId must not be null");
        this.instrumentId = Objects.requireNonNull(instrumentId, "instrumentId must not be null");
        this.quantity = quantity;
        this.pricePerUnit = pricePerUnit;
        this.overallGains = overallGains;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = this.createdAt;
    }
    public Long getId() {
        return id;
    }

    public UUID getClientId() {
        return clientId;
    }

    public Long getInstrumentId() {
        return instrumentId;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getPricePerUnit() {
        return pricePerUnit;
    }

    public BigDecimal getOverallGains() {
        return overallGains;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    /**
     * Recomputes overall gains against a live market price:
     * (currentPrice - pricePerUnit) * quantity. Shared by both subclasses
     * since the formula doesn't differ - only how each one's quantity
     * moves does.
     */
    public void calculateOverallGains(BigDecimal currentPrice) {
        BigDecimal normalizedPrice = currentPrice;
        this.overallGains = normalizedPrice.subtract(pricePerUnit)
                .multiply(BigDecimal.valueOf(quantity))
                .setScale(2, RoundingMode.HALF_UP);
        touch();
    }

    protected void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    protected void touch() {
        this.updatedAt = LocalDateTime.now();
    }

}