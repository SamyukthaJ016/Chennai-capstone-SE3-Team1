package com.team1.trading.api.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * Response body for {@code GET /api/v1/accounts/{id}}, as fixed by contracts/trade-api.yaml.
 * {@link #accountId} is the one field in the contract where the name means the string business
 * identifier ({@code ACCOUNTS.account_id}) and not the numeric key; {@link #id} is the key.
 */
public class AccountResponse {

    private Long id;
    private String accountId;
    private String holderName;
    private BigDecimal cashBalance;
    private String status;
    private Integer version;
    private LocalDateTime lastUpdated;

    public AccountResponse() {
    }

    public AccountResponse(Long id, String accountId, String holderName, BigDecimal cashBalance,
                           String status, Integer version, LocalDateTime lastUpdated) {
        this.id = id;
        this.accountId = accountId;
        this.holderName = holderName;
        this.cashBalance = cashBalance;
        this.status = status;
        this.version = version;
        this.lastUpdated = lastUpdated;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getAccountId() {
        return accountId;
    }

    public void setAccountId(String accountId) {
        this.accountId = accountId;
    }

    public String getHolderName() {
        return holderName;
    }

    public void setHolderName(String holderName) {
        this.holderName = holderName;
    }

    public BigDecimal getCashBalance() {
        return cashBalance;
    }

    public void setCashBalance(BigDecimal cashBalance) {
        this.cashBalance = cashBalance;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Integer getVersion() {
        return version;
    }

    public void setVersion(Integer version) {
        this.version = version;
    }

    public LocalDateTime getLastUpdated() {
        return lastUpdated;
    }

    public void setLastUpdated(LocalDateTime lastUpdated) {
        this.lastUpdated = lastUpdated;
    }
}