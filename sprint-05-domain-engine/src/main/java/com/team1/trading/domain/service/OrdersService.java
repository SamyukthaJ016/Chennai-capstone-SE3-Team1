package com.team1.trading.domain.service;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Owns the orders and the idempotency keys they were accepted under.
 *
 * Business rule 8 turns on claimIdempotencyKey, and it is a claim rather than
 * a lookup on purpose. Backed by a database the authority is the unique
 * constraint on orders.idempotency_key: the write is attempted and reports
 * whether it won, because two concurrent requests carrying the same key both
 * pass a read-then-write check and losing that race duplicates a trade.
 *
 * Here the same seam is a concurrent set, whose add() is atomic, so exactly
 * one of any number of callers is told it got the key. There is deliberately
 * no exists(key) method for rule 8 to be tempted by.
 */
public class OrdersService {

    private final Set<String> claimedKeys = ConcurrentHashMap.newKeySet();

    /**
     * Claims the key for the order about to be recorded.
     *
     * @return true if this caller got the key, false if it was already taken,
     *         which is business rule 8 failing.
     */
    public boolean claimIdempotencyKey(String idempotencyKey) {
        return idempotencyKey != null && claimedKeys.add(idempotencyKey);
    }

    /** Whether any order has been accepted under this key. Never used by rule 8. */
    public int claimedKeyCount() {
        return claimedKeys.size();
    }
}
