package com.team1.trading.domain.service;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class OrdersService {

    private final Set<String> claimedKeys = ConcurrentHashMap.newKeySet();

    public boolean claimIdempotencyKey(String idempotencyKey) {
        return idempotencyKey != null && claimedKeys.add(idempotencyKey);
    }

    public int claimedKeyCount() {
        return claimedKeys.size();
    }
}
