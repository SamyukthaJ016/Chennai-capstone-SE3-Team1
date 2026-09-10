package com.team1.trading.domain.exception;

public class OrderNotFoundException extends DomainException {

    public static final String CODE = "ORD-409";
    public static final String MESSAGE = "Order not found";

    private final String orderId;

    public OrderNotFoundException(String orderId) {
        super(CODE, MESSAGE);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}