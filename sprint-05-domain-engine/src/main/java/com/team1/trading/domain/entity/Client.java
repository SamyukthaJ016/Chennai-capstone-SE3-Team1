package com.team1.trading.domain.entity;

import java.math.BigDecimal;
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

}
