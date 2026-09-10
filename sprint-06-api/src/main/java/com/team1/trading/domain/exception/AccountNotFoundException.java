package com.team1.trading.domain.exception;

public class AccountNotFoundException extends DomainException {

    public static final String CODE = "ACC-404";
    public static final String MESSAGE = "Account not found";

    private final Long accountId;

    public AccountNotFoundException(Long accountId) {
        super(CODE, MESSAGE);
        this.accountId = accountId;
    }

    public Long getAccountId() {
        return accountId;
    }
}
