package com.team1.trading.domain.entity;

import java.math.BigDecimal;

public class PortfolioPosition extends PortfolioEntry {

    public PortfolioPosition(Long positionId, Long clientId, String instrumentId, int quantity, BigDecimal pricePerUnit) {
        super(positionId, clientId, instrumentId, quantity, pricePerUnit);
    }

    public Long getPositionId() {
        return getId();
    }

}
