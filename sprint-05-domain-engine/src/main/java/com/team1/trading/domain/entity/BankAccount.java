package com.team1.trading.domain.entity;

import java.math.BigDecimal;
import java.util.Objects;

public class BankAccount {

    private Long clientId;
    private String accountNumber;
    private String name;
    private String phone;
    private String email;
    private BigDecimal accountBalance;
    private String bankName;
    private String ifscCode;

    public BankAccount(Long clientId, String accountNumber, String name, String phone,
                       String email, String bankName, String ifscCode) {
        this.clientId = Objects.requireNonNull(clientId, "clientId must not be null");
        this.accountNumber =  Objects.requireNonNull(accountNumber, "accountNumber must not be null");
        this.name = name;
        this.phone = phone;
        this.email = email;
        this.bankName = bankName;
        this.ifscCode = ifscCode;
        this.accountBalance = BigDecimal.ZERO;
    }

    public BankAccount(Long clientId, String accountNumber, String name, String phone, String email,
                       BigDecimal accountBalance, String bankName, String ifscCode) {
        this.clientId = Objects.requireNonNull(clientId, "clientId must not be null");
        this.accountNumber = Objects.requireNonNull(accountNumber, "accountNumber must not be null");
        this.name = name;
        this.phone = phone;;
        this.email = email;
        this.accountBalance = accountBalance;
        this.bankName = bankName;
        this.ifscCode = ifscCode;
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

    public String getPhone() {
        return phone;
    }

    public String getEmail() {
        return email;
    }

    public String getBankName() {
        return bankName;
    }

    public String getIfscCode() {
        return ifscCode;
    }

    /** Current balance. Matches the diagram's getBalance(). */
    public BigDecimal getBalance() {
        return accountBalance;
    }

    /** Refused before anything is added if the amount isn't positive. */
    public void deposit(BigDecimal amount) {
        this.accountBalance = accountBalance.add(amount);
    }

    /** Refused before anything is subtracted if it would go negative. */
    public void withdraw(BigDecimal amount) {
        this.accountBalance = accountBalance.subtract(amount);
    }

    public void updateContact(String phone, String email) {
        this.phone = phone;
        this.email = email;
    }
}