package com.team1.trading.api.dto;

/**
 * The single error envelope for every failure, as fixed by contracts/trade-api.yaml.
 *
 * <p>Clients branch on {@link #errorCode}, never on the message and never on the HTTP status
 * alone, since 404 and 409 each carry more than one code. The body carries exactly these two
 * fields and nothing else: no stack trace, no class name, no SQL fragment, no internal
 * identifier.
 */
public class ErrorResponse {

    private String errorCode;
    private String message;

    public ErrorResponse() {
    }

    public ErrorResponse(String errorCode, String message) {
        this.errorCode = errorCode;
        this.message = message;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public void setErrorCode(String errorCode) {
        this.errorCode = errorCode;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}