package com.team1.trading.domain.exception;

/** Rule 2, ACC-403: the account exists but is SUSPENDED or INACTIVE. */
public class AccountNotActiveException extends DomainException {

    public static final String CODE = "ACC-403";
    public static final String MESSAGE = "Account not active";

    private final Long accountId;
    private final String accountState;

    public AccountNotActiveException(Long accountId, String accountState) {
        super(CODE, MESSAGE);
        this.accountId = accountId;
        this.accountState = accountState;
    }

    public Long getAccountId() {
        return accountId;
    }

    /** Which state it was in. For the server log. */
    public String getAccountState() {
        return accountState;
    }
}
