package com.team1.trading.api.exception;

import com.team1.trading.api.dto.ErrorResponse;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.AuthenticationException;
import com.team1.trading.domain.exception.DomainException;
import com.team1.trading.domain.exception.DuplicateOrderException;
import com.team1.trading.domain.exception.InstrumentNotFoundException;
import com.team1.trading.domain.exception.InsufficientFundsException;
import com.team1.trading.domain.exception.InsufficientHoldingsException;
import com.team1.trading.domain.exception.InvalidOrderException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;

/**
 * Single error handler for the whole platform, as contracts/trade-api.yaml requires.
 *
 * <p>Every failure leaves the error envelope {@code {"errorCode", "message"}} and nothing else:
 * no whitelabel page, no stack trace, no bare status with an empty body. The message returned to
 * the client is always the catalogued human string; whatever an investigation needs about the
 * internal state is logged on the server and never reaches the body.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger LOG = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    private static final String VALIDATION_MESSAGE = "Invalid input";
    private static final String INTERNAL_MESSAGE = "Internal error";

    /**
     * Every domain exception maps through the catalogue to its documented HTTP status. 404 is
     * shared by {@code ACC-404} and {@code INS-404}, and 409 carries {@code ORD-409}, so the
     * client branches on {@code errorCode}, never on the status alone.
     */
    @ExceptionHandler(DomainException.class)
    public ResponseEntity<ErrorResponse> handleDomainException(DomainException e) {
        HttpStatus status = ErrorCatalogue.statusFor(e.getCode());
        LOG.warn("Rejected request [code={}] {}", e.getCode(), detailFor(e), e);
        return envelope(e.getCode(), e.getMessage(), status);
    }

    /**
     * Bean-validation failures from {@code @Valid} on a request body map to {@code VAL-422}.
     * The offending fields are logged server-side; the client sees only the catalogued message.
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException e) {
        List<FieldError> fieldErrors = e.getBindingResult().getFieldErrors();
        LOG.warn("Request validation failed fieldErrors={} message={}", fieldErrors, e.getMessage(), e);
        return envelope(ErrorCatalogue.VAL_422, VALIDATION_MESSAGE, HttpStatus.UNPROCESSABLE_ENTITY);
    }

    /**
     * Anything not covered above leaves the envelope too, so no whitelabel page can ever reach a
     * client. The code {@code INTERNAL-500} is not part of the documented catalogue; it exists so
     * an unforeseen failure is still an envelope the Angular application can handle.
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleUnexpected(Exception e) {
        LOG.error("Unhandled exception", e);
        return envelope(ErrorCatalogue.INTERNAL_500, INTERNAL_MESSAGE, HttpStatus.INTERNAL_SERVER_ERROR);
    }

    private static ResponseEntity<ErrorResponse> envelope(String code, String message, HttpStatus status) {
        return ResponseEntity.status(status).body(new ErrorResponse(code, message));
    }

    /**
     * The internal state that an investigation needs, collected on the server only. The fields
     * here (account keys, symbols, amounts, idempotency keys) must never appear in a response
     * body.
     */
    private static String detailFor(DomainException e) {
        if (e instanceof AccountNotFoundException x) {
            return "accountId=" + x.getAccountId();
        }
        if (e instanceof AccountNotActiveException x) {
            return "accountId=" + x.getAccountId() + ", state=" + x.getAccountState();
        }
        if (e instanceof InstrumentNotFoundException x) {
            return "symbol=" + x.getSymbol();
        }
        if (e instanceof InsufficientFundsException x) {
            return "accountId=" + x.getAccountId()
                    + ", required=" + x.getRequired()
                    + ", available=" + x.getAvailable();
        }
        if (e instanceof InsufficientHoldingsException x) {
            return "accountId=" + x.getAccountId()
                    + ", symbol=" + x.getSymbol()
                    + ", requested=" + x.getRequested()
                    + ", held=" + x.getHeld();
        }
        if (e instanceof DuplicateOrderException x) {
            return "idempotencyKey=" + x.getIdempotencyKey();
        }
        if (e instanceof InvalidOrderException x) {
            return "field=" + x.getField() + ", rejectedValue=" + x.getRejectedValue();
        }
        if (e instanceof AuthenticationException x) {
            return "reason=" + x.getReason();
        }
        return "exception=" + e.getClass().getSimpleName();
    }
}