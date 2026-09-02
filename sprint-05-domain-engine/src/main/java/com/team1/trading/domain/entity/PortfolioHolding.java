package com.team1.trading.domain.entity;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.UUID;

public class PortfolioHolding extends PortfolioEntry {

    public PortfolioHolding(Long holdingId, UUID clientId, Long instrumentId, int quantity, BigDecimal pricePerUnit) {
        super(holdingId, clientId, instrumentId, quantity, pricePerUnit);
    }

    public Long getHoldingId() {
        return getId();
    }

    public void incrementQuantity(int qty) {
        if (qty <= 0) {
            throw new IllegalArgumentException("qty must be greater than zero");
        }
        setQuantity(getQuantity() + qty);
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