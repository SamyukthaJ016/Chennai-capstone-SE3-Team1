package com.team1.trading.domain.entity;

import com.team1.trading.domain.entity.types.AccountState;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.UUID;

public class Client {

    private final UUID clientId;
    private Long userId;
    private Integer accountNumber;
    private String name;
    private String email;
    private String phone;
    private LocalDateTime createdOn;
    private String accountState;
    private BigDecimal walletBalance;

    /** For a brand-new client - generates its own identifier. */
    public Client(Long userId, Integer accountNumber, String name, String email, String phone) {
        this.clientId = UUID.randomUUID();
        this.userId = userId;
        this.accountNumber = Objects.requireNonNull(accountNumber, "accountNumber must not be null");
        this.name = name;
        this.email = email;
        this.phone = phone;
        this.createdOn = LocalDateTime.now();
        this.accountState = "ACTIVE";
        this.walletBalance = BigDecimal.ZERO.setScale(2, java.math.RoundingMode.UNNECESSARY);
    }

    /** For reconstructing a client already in storage, with its existing id. */
    public Client(UUID clientId, Long userId, Integer accountNumber, String name, String email, String phone,
                  LocalDateTime createdOn, String accountState, BigDecimal walletBalance) {
        this.clientId = Objects.requireNonNull(clientId, "clientId must not be null");
        this.userId = userId;
        this.accountNumber = Objects.requireNonNull(accountNumber, "accountNumber must not be null");
        this.name = name;
        this.email = email;
        this.phone = phone;
        this.createdOn = createdOn;
        this.accountState = accountState;
        this.walletBalance = walletBalance;
    }

    public UUID getClientId() {
        return clientId;
    }

    /** The numeric key orders.user_id references. */
    public Long getUserId() {
        return userId;
    }

    public Integer getAccountNumber() {
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

    /** Business rule 2 asks this. Only an ACTIVE account trades. */
    public boolean canTrade() {
        return AccountState.ACTIVE.name().equals(accountState);
    }

    /** Lifts a suspension. The suspension is reversible. */
    public void activate() {
        this.accountState = AccountState.ACTIVE.name();
    }

    /** The account can still be read, it just cannot trade. */
    public void suspend() {
        this.accountState = AccountState.SUSPENDED.name();
    }

    public void deactivate() {
        this.accountState = AccountState.INACTIVE.name();
    }

    /**
     * Whether the wallet covers the amount. Business rule 6 asks this before a
     * buy, so nothing is subtracted to find out. Exactly the balance is
     * affordable; a penny more is not.
     */
    public boolean canAfford(BigDecimal amount) {
        return walletBalance.compareTo(money(amount)) >= 0;
    }

    /** Puts money in. Zero is allowed and moves nothing. */
    public void credit(BigDecimal amount) {
        this.walletBalance = money(walletBalance.add(money(amount)));
    }

    /**
     * Takes money out. A debit that would leave the balance negative is
     * refused before anything is subtracted, rather than attempted and then
     * inspected for a negative result.
     */
    public void debit(BigDecimal amount) {
        BigDecimal value = money(amount);
        if (walletBalance.compareTo(value) < 0) {
            throw new IllegalStateException(
                    "balance " + walletBalance + " cannot cover a debit of " + value);
        }
        this.walletBalance = money(walletBalance.subtract(value));
    }

    /**
     * Money is decimal at two places and never a double, because binary
     * floating point cannot represent 0.10 exactly and a balance out by a
     * hundredth of a penny after a thousand trades is a defect an auditor
     * finds first. An absent or negative amount is not money.
     */
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
