package com.team1.trading.domain.entity;

import java.math.BigDecimal;

public class TransactionSuccess extends Transaction {

    private final BigDecimal quantity;
    private final BigDecimal pricePerUnit;

    public TransactionSuccess(Long transactionId, Long orderId, BigDecimal quantity, BigDecimal pricePerUnit) {
        super(transactionId, orderId);
        this.quantity = quantity;
        this.pricePerUnit = pricePerUnit;
    }

    public BigDecimal getQuantity() {
        return quantity;
    }

    public BigDecimal getPricePerUnit() {
        return pricePerUnit;
    }

    // settle() and generateReceipt() intentionally left out - need to know
    // what each actually does before implementing.

}