package com.team1.trading.api.dto;

import java.math.BigDecimal;

/**
 * One entry of {@code GET /api/v1/accounts/{id}/positions}, as fixed by contracts/trade-api.yaml.
 * Net held quantity and weighted average cost basis per instrument. Positions with a net quantity
 * of zero are never returned.
 */
public class PositionResponse {

    private Long accountId;
    private String symbol;
    private Integer quantity;
    private BigDecimal averageCost;

    public PositionResponse() {
    }

    public PositionResponse(Long accountId, String symbol, Integer quantity, BigDecimal averageCost) {
        this.accountId = accountId;
        this.symbol = symbol;
        this.quantity = quantity;
        this.averageCost = averageCost;
    }

    public Long getAccountId() {
        return accountId;
    }

    public void setAccountId(Long accountId) {
        this.accountId = accountId;
    }

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public BigDecimal getAverageCost() {
        return averageCost;
    }

    public void setAverageCost(BigDecimal averageCost) {
        this.averageCost = averageCost;
    }
}