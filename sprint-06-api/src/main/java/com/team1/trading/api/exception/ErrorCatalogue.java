package com.team1.trading.api.exception;

import org.springframework.http.HttpStatus;

import java.util.Collections;
import java.util.Map;

/**
 * Maps every documented error code to the HTTP status it is served under, as fixed by
 * contracts/trade-api.yaml.
 *
 * <p>This is the single source of truth for the error catalogue. Clients branch on the code,
 * never on the status alone, because 404 and 409 each carry more than one code. The
 * {@link GlobalExceptionHandler} resolves every {@code DomainException} through this table, so
 * adding a code anywhere else is a drift that review should catch.
 */
public final class ErrorCatalogue {

    public static final String ACC_404 = "ACC-404";
    public static final String ACC_403 = "ACC-403";
    public static final String INS_404 = "INS-404";
    public static final String ORD_400 = "ORD-400";
    public static final String ORD_409 = "ORD-409";
    public static final String VAL_422 = "VAL-422";
    public static final String AUTH_401 = "AUTH-401";

    public static final String INTERNAL_500 = "INTERNAL-500";

    private static final Map<String, HttpStatus> STATUS_BY_CODE = Map.of(
            ACC_404, HttpStatus.NOT_FOUND,
            ACC_403, HttpStatus.FORBIDDEN,
            INS_404, HttpStatus.NOT_FOUND,
            ORD_400, HttpStatus.BAD_REQUEST,
            ORD_409, HttpStatus.CONFLICT,
            VAL_422, HttpStatus.UNPROCESSABLE_ENTITY,
            AUTH_401, HttpStatus.UNAUTHORIZED,
            INTERNAL_500, HttpStatus.INTERNAL_SERVER_ERROR
    );

    private ErrorCatalogue() {
    }

    /**
     * The HTTP status a documented error code is served under.
     *
     * <p>Two codes are served under 404 ({@code ACC-404}, {@code INS-404}) and one under 409
     * ({@code ORD-409}), which is why clients must branch on the code rather than the status.
     * An unknown code is treated as an internal error rather than silently mapped to a
     * documented status that would lie to the client.
     */
    public static HttpStatus statusFor(String errorCode) {
        return STATUS_BY_CODE.getOrDefault(errorCode, HttpStatus.INTERNAL_SERVER_ERROR);
    }

    /**
     * Read-only view of the catalogue, one entry per code.
     */
    public static Map<String, HttpStatus> asMap() {
        return Collections.unmodifiableMap(STATUS_BY_CODE);
    }
}