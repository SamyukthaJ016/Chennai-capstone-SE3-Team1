package com.team1.trading.domain.entity;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.Objects;

/**
 * Common shape shared by PortfolioHolding and PortfolioPosition: a
 * client's stake in one instrument, tracked by quantity, average price
 * paid, and gains against the current market price.
 */
public abstract class PortfolioEntry {

    private final Long portifolioid;
    private final Long clientId;
    private final String instrumentId;
    private int quantity;
    private BigDecimal pricePerUnit;
    private BigDecimal overallGains;
    private final LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    protected PortfolioEntry(Long portifolioid, Long clientId, String instrumentId, int quantity, BigDecimal pricePerUnit) {
        this.portifolioid = portifolioid;
        this.clientId = Objects.requireNonNull(clientId, "userId must not be null");
        this.instrumentId = Objects.requireNonNull(instrumentId, "instrumentId must not be null");
        this.quantity = quantity;
        this.pricePerUnit = pricePerUnit;
        this.overallGains = BigDecimal.ZERO;
        this.createdAt = LocalDateTime.now();
        this.updatedAt = this.createdAt;
    }

    public Long getId() {
        return portifolioid;
    }

    public Long getUserId() {
        return clientId;
    }

    public String getInstrumentId() {
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
        this.overallGains = currentPrice.subtract(pricePerUnit)
                .multiply(BigDecimal.valueOf(quantity))
                .setScale(2, RoundingMode.HALF_UP);
        touch();
    }

    protected void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    protected void setPricePerUnit(BigDecimal pricePerUnit) {
        this.pricePerUnit = pricePerUnit;
    }

    protected void touch() {
        this.updatedAt = LocalDateTime.now();
    }
}