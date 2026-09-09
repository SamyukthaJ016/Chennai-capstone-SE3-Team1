package com.team1.trading.api.controller;

import com.team1.trading.api.dto.AccountResponse;
import com.team1.trading.api.dto.BalanceResponse;
import com.team1.trading.api.dto.OrderHistoryEntry;
import com.team1.trading.api.dto.PositionResponse;
import com.team1.trading.api.security.TokenAccountIdResolver;
import com.team1.trading.api.service.AccountService;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.List;

/**
 * The four account read endpoints of contracts/trade-api.yaml under {@code /api/v1/accounts}:
 * details, cash balance, positions and order history.
 */
@RestController
@RequestMapping("/api/v1/accounts")
public class AccountController {

    private final AccountService accountService;
    private final TokenAccountIdResolver tokenAccountIdResolver;

    public AccountController(AccountService accountService, TokenAccountIdResolver tokenAccountIdResolver) {
        this.accountService = accountService;
        this.tokenAccountIdResolver = tokenAccountIdResolver;
    }

    @GetMapping("/{id}")
    public ResponseEntity<AccountResponse> getAccount(@PathVariable("id") Long id,
                                                      @RequestHeader(value = "Authorization", required = false)
                                                      String authorization) {
        return ResponseEntity.ok(accountService.getAccount(id, tokenAccountIdResolver.resolve(authorization)));
    }

    @GetMapping("/{id}/balance")
    public ResponseEntity<BalanceResponse> getBalance(@PathVariable("id") Long id,
                                                      @RequestHeader(value = "Authorization", required = false)
                                                      String authorization) {
        return ResponseEntity.ok(accountService.getBalance(id, tokenAccountIdResolver.resolve(authorization)));
    }

    @GetMapping("/{id}/positions")
    public ResponseEntity<List<PositionResponse>> getPositions(@PathVariable("id") Long id,
                                                               @RequestHeader(value = "Authorization", required = false)
                                                               String authorization) {
        return ResponseEntity.ok(accountService.getPositions(id, tokenAccountIdResolver.resolve(authorization)));
    }

    @GetMapping("/{id}/orders")
    public ResponseEntity<List<OrderHistoryEntry>> getOrders(
            @PathVariable("id") Long id,
            @RequestParam(value = "status", required = false) String status,
            @RequestParam(value = "from", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime from,
            @RequestParam(value = "to", required = false)
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) LocalDateTime to,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        return ResponseEntity.ok(accountService.getOrderHistory(
                id, tokenAccountIdResolver.resolve(authorization), status, from, to));
    }
}