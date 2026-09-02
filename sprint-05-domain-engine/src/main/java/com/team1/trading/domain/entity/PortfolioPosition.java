package com.team1.trading.domain.entity;

import java.math.BigDecimal;
import java.util.UUID;


public class PortfolioPosition extends PortfolioEntry {

    public PortfolioPosition(Long positionId, UUID clientId, String instrumentId, int quantity, BigDecimal pricePerUnit) {
        super(positionId, clientId, instrumentId, quantity, pricePerUnit);
    }

    public Long getPositionId() {
        return getId();
    }

    // updatePosition() left out - the diagram doesn't say what it does
    // beyond what calculateOverallGains(currentPrice) already covers,
    // which this class inherits. Tell me what's different about it.
}