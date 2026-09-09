package com.team1.trading.domain.exception;

/**
 * A token is missing, malformed, expired or wrongly signed. All four cases answer the one
 * code {@code AUTH-401} with the same message, because a more specific answer tells an
 * attacker which of the four they got wrong. The distinguishing reason is logged on the
 * server only.
 */
public class AuthenticationException extends DomainException {

    public static final String CODE = "AUTH-401";
    public static final String MESSAGE = "Unauthorised";

    private final String reason;

    public AuthenticationException(String reason) {
        super(CODE, MESSAGE);
        this.reason = reason;
    }

    public String getReason() {
        return reason;
    }
}