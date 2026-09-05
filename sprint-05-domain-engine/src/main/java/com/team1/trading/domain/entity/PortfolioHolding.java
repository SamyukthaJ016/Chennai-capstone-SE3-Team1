package com.team1.trading.domain.entity;

import java.math.BigDecimal;
import java.math.RoundingMode;

public class PortfolioHolding extends PortfolioEntry {

    public PortfolioHolding(Long holdingId, long clientId, String instrumentId, int quantity, BigDecimal pricePerUnit) {
        super(holdingId, clientId, instrumentId, quantity, pricePerUnit);
    }

    public Long getHoldingId() {
        return getId();
    }

    /**
     * A buy. Recalculates the average cost across the old holding and the
     * new units at the price they were bought at; a sell (decrementQuantity)
     * leaves the average alone.
     */
    public void incrementQuantity(int qty, BigDecimal priceAtBuy) {
        if (qty <= 0) {
            throw new IllegalArgumentException("qty must be greater than zero");
        }
        if (priceAtBuy == null || priceAtBuy.signum() <= 0) {
            throw new IllegalArgumentException("priceAtBuy must be greater than zero");
        }
        int oldQty = getQuantity();
        BigDecimal oldCost = getPricePerUnit().multiply(BigDecimal.valueOf(oldQty));
        BigDecimal newCost = priceAtBuy.multiply(BigDecimal.valueOf(qty));
        int newQty = oldQty + qty;
        BigDecimal newAverage = oldCost.add(newCost)
                .divide(BigDecimal.valueOf(newQty), 2, RoundingMode.HALF_UP);
        setQuantity(newQty);
        setPricePerUnit(newAverage);
        touch();
    }

    public void decrementQuantity(int qty) {
        if (qty <= 0) {
            throw new IllegalArgumentException("qty must be greater than zero");
        }
        if (qty > getQuantity()) {
            throw new IllegalStateException("cannot decrement by " + qty + ", only " + getQuantity() + " held");
        }
        setQuantity(getQuantity() - qty);
        touch();
    }

    public BigDecimal calculateHoldingValue(BigDecimal marketPrice) {
        BigDecimal normalizedPrice = marketPrice;
        return normalizedPrice.multiply(BigDecimal.valueOf(getQuantity())).setScale(2, RoundingMode.HALF_UP);
    }
}