package com.team1.trading.domain.exception;

public class OrderNotCancellableException extends DomainException {

    public static final String CODE = "ORD-409";
    public static final String MESSAGE = "Order is not cancellable";

    private final String orderId;
    private final String status;

    public OrderNotCancellableException(String orderId, String status) {
        super(CODE, MESSAGE);
        this.orderId = orderId;
        this.status = status;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getStatus() {
        return status;
    }
}