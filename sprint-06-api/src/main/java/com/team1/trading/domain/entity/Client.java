package com.team1.trading.domain.entity;

import com.team1.trading.domain.entity.types.AccountStatus;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.Objects;

public class Client {

    private Long clientId;
    private String accountNumber;
    private String name;
    private String email;
    private String phone;
    private LocalDateTime createdOn;
    private String accountState;
    private BigDecimal walletBalance;

    public Client(Long clientId, String accountNumber, String name, String email, String phone) {
        this.clientId = clientId;
        this.accountNumber = Objects.requireNonNull(accountNumber, "accountNumber must not be null");
        this.name = name;
        this.email = email;
        this.phone = phone;
        this.createdOn = LocalDateTime.now();
        this.accountState = "ACTIVE";
        this.walletBalance = BigDecimal.ZERO.setScale(2, RoundingMode.UNNECESSARY);
    }

    public Client(Long clientId, String accountNumber, String name, String email, String phone,
                  LocalDateTime createdOn, String accountState, BigDecimal walletBalance) {
        this.clientId = clientId;
        this.accountNumber = Objects.requireNonNull(accountNumber, "accountNumber must not be null");
        this.name = name;
        this.email = email;
        this.phone = phone;
        this.createdOn = createdOn;
        this.accountState = accountState;
        this.walletBalance = walletBalance;
    }

    public Long getClientId() {
        return clientId;
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public String getPhone() {
        return phone;
    }

    public LocalDateTime getCreatedOn() {
        return createdOn;
    }

    public String getAccountState() {
        return accountState;
    }

    public BigDecimal getWalletBalance() {
        return walletBalance;
    }

    public void updateProfile(String name, String email, String phone) {
        this.name = name;
        this.email = email;
        this.phone = phone;
    }

    public boolean canTrade() {
        return AccountStatus.ACTIVE.name().equals(accountState);
    }

    public void activate() {
        this.accountState = AccountStatus.ACTIVE.name();
    }

    public void suspend() {
        this.accountState = AccountStatus.SUSPENDED.name();
    }

    public void close() {
        this.accountState = AccountStatus.CLOSED.name();
    }

    public boolean canAfford(BigDecimal amount) {
        return walletBalance.compareTo(money(amount)) >= 0;
    }

    public void credit(BigDecimal amount) {
        this.walletBalance = money(walletBalance.add(money(amount)));
    }

    public void debit(BigDecimal amount) {
        BigDecimal value = money(amount);
        if (walletBalance.compareTo(value) < 0) {
            throw new IllegalStateException(
                    "balance " + walletBalance + " cannot cover a debit of " + value);
        }
        this.walletBalance = money(walletBalance.subtract(value));
    }

    private static BigDecimal money(BigDecimal amount) {
        if (amount == null) {
            throw new IllegalArgumentException("amount must not be null");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative: " + amount);
        }
        return amount.setScale(2, RoundingMode.HALF_UP);
    }
}
