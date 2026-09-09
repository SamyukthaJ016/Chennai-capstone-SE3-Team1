package com.team1.trading.api.dto;

import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;

import java.math.BigDecimal;

/**
 * Response body for {@code POST /api/v1/orders} and {@code DELETE /api/v1/orders/{id}}, as
 * fixed by contracts/trade-api.yaml. The identifier is the stored UUID displayed with an
 * {@code ORD-} prefix.
 */
public class OrderResponse {

    private String orderId;
    private OrderStatus status;
    private String message;
    private String symbol;
    private OrderSide side;
    private Integer quantity;
    private BigDecimal price;

    public OrderResponse() {
    }

    public OrderResponse(String orderId, OrderStatus status, String message,
                         String symbol, OrderSide side, Integer quantity, BigDecimal price) {
        this.orderId = orderId;
        this.status = status;
        this.message = message;
        this.symbol = symbol;
        this.side = side;
        this.quantity = quantity;
        this.price = price;
    }

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public String getSymbol() {
        return symbol;
    }

    public void setSymbol(String symbol) {
        this.symbol = symbol;
    }

    public OrderSide getSide() {
        return side;
    }

    public void setSide(OrderSide side) {
        this.side = side;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}