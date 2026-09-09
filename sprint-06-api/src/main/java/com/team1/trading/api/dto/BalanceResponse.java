package com.team1.trading.api.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * Response body for {@code GET /api/v1/accounts/{id}/balance}, as fixed by contracts/trade-api.yaml.
 * Available cash only; it never includes the market value of holdings.
 */
public class BalanceResponse {

    private Long accountId;
    private BigDecimal cashBalance;
    private String currency;
    private LocalDateTime asOf;

    public BalanceResponse() {
    }

    public BalanceResponse(Long accountId, BigDecimal cashBalance, String currency, LocalDateTime asOf) {
        this.accountId = accountId;
        this.cashBalance = cashBalance;
        this.currency = currency;
        this.asOf = asOf;
    }

    public Long getAccountId() {
        return accountId;
    }

    public void setAccountId(Long accountId) {
        this.accountId = accountId;
    }

    public BigDecimal getCashBalance() {
        return cashBalance;
    }

    public void setCashBalance(BigDecimal cashBalance) {
        this.cashBalance = cashBalance;
    }

    public String getCurrency() {
        return currency;
    }

    public void setCurrency(String currency) {
        this.currency = currency;
    }

    public LocalDateTime getAsOf() {
        return asOf;
    }

    public void setAsOf(LocalDateTime asOf) {
        this.asOf = asOf;
    }
}