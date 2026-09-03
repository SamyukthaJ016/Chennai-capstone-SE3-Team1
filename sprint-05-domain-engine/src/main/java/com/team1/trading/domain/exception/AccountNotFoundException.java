package com.team1.trading.domain.exception;

/** Rule 1, ACC-404: no account exists with the key on the request. */
public class AccountNotFoundException extends DomainException {

    public static final String CODE = "ACC-404";
    public static final String MESSAGE = "Account not found";

    private final Long accountId;

    public AccountNotFoundException(Long accountId) {
        super(CODE, MESSAGE);
        this.accountId = accountId;
    }

    /** For the server log, not for the response body. */
    public Long getAccountId() {
        return accountId;
    }
}
