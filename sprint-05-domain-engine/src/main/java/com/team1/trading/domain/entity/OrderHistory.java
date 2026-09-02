package com.team1.trading.domain.entity;

import com.team1.trading.domain.entity.types.OrderStatus;

import java.time.LocalDateTime;
import java.util.Objects;

/**
 * One row of the audit trail for one order. Replaces what the in_progress,
 * transaction_success and transaction_failure tables recorded between them.
 *
 * api_response holds the raw JSON the external API returned, kept as text -
 * this module carries it and never parses it.
 */
public class OrderHistory {

    private Long historyId;
    private Long orderId;
    private String eventType;
    private OrderStatus previousStatus;
    private OrderStatus newStatus;
    private String externalStatus;
    private String externalOrderId;
    private String requestId;
    private String failureCode;
    private String failureReason;
    private String apiResponse;
    private LocalDateTime eventTimestamp;
    private LocalDateTime createdAt;

    public OrderHistory(Long historyId, Long orderId, String eventType,
                        OrderStatus previousStatus, OrderStatus newStatus,
                        String externalStatus, String externalOrderId, String requestId,
                        String failureCode, String failureReason, String apiResponse) {
        this.historyId = historyId;
        this.orderId = Objects.requireNonNull(orderId, "orderId must not be null");
        this.eventType = eventType;
        this.previousStatus = previousStatus;
        this.newStatus = newStatus;
        this.externalStatus = externalStatus;
        this.externalOrderId = externalOrderId;
        this.requestId = requestId;
        this.failureCode = failureCode;
        this.failureReason = failureReason;
        this.apiResponse = apiResponse;
        this.eventTimestamp = LocalDateTime.now();
        this.createdAt = this.eventTimestamp;
    }

    public Long getHistoryId() { return historyId; }
    public Long getOrderId() { return orderId; }
    public String getEventType() { return eventType; }
    public OrderStatus getPreviousStatus() { return previousStatus; }
    public OrderStatus getNewStatus() { return newStatus; }
    public String getExternalStatus() { return externalStatus; }
    public String getExternalOrderId() { return externalOrderId; }
    public String getRequestId() { return requestId; }
    public String getFailureCode() { return failureCode; }
    public String getFailureReason() { return failureReason; }
    public String getApiResponse() { return apiResponse; }
    public LocalDateTime getEventTimestamp() { return eventTimestamp; }
    public LocalDateTime getCreatedAt() { return createdAt; }

}
