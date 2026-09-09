package com.team1.trading.api.service;

import com.team1.trading.api.dto.AccountResponse;
import com.team1.trading.api.dto.BalanceResponse;
import com.team1.trading.api.dto.OrderHistoryEntry;
import com.team1.trading.api.dto.PositionResponse;
import com.team1.trading.api.mapper.AccountMapper;
import com.team1.trading.api.mapper.AccountMapper.AccountRow;
import com.team1.trading.api.mapper.OrderMapper;
import com.team1.trading.api.mapper.OrderMapper.OrderHistoryFilter;
import com.team1.trading.api.mapper.OrderMapper.OrderRow;
import com.team1.trading.api.mapper.PositionMapper;
import com.team1.trading.domain.entity.Client;
import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.InvalidOrderException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * Read endpoints for contracts/trade-api.yaml: account details, cash balance, positions and the
 * order history audit trail.
 *
 * <p>Every read first proves the account exists and is reachable with the caller's token
 * ({@code ACC-404}/{@code ACC-403}), then answers from the tables. Activeness is decided by the
 * domain's {@link Client#canTrade()} method, never reimplemented here.
 */
@Service
public class AccountService {

    private final AccountMapper accountMapper;
    private final OrderMapper orderMapper;
    private final PositionMapper positionMapper;
    private final String currency;

    public AccountService(AccountMapper accountMapper, OrderMapper orderMapper,
                          PositionMapper positionMapper,
                          @Value("${trade.currency:USD}") String currency) {
        this.accountMapper = accountMapper;
        this.orderMapper = orderMapper;
        this.positionMapper = positionMapper;
        this.currency = currency;
    }

    public AccountResponse getAccount(Long accountId, Long tokenAccountId) {
        AccountRow row = resolve(accountId, tokenAccountId);
        return new AccountResponse(row.getClientId(), row.getAccountNumber(), row.getName(),
                row.getWalletBalance(), row.getAccountState(), row.getVersion(), row.getUpdatedOn());
    }

    public BalanceResponse getBalance(Long accountId, Long tokenAccountId) {
        AccountRow row = resolve(accountId, tokenAccountId);
        return new BalanceResponse(row.getClientId(), row.getWalletBalance(), currency, LocalDateTime.now());
    }

    public List<PositionResponse> getPositions(Long accountId, Long tokenAccountId) {
        resolve(accountId, tokenAccountId);
        return positionMapper.listPositions(accountId);
    }

    public List<OrderHistoryEntry> getOrderHistory(Long accountId, Long tokenAccountId,
                                                   String status, LocalDateTime from, LocalDateTime to) {
        resolve(accountId, tokenAccountId);
        OrderHistoryFilter filter = new OrderHistoryFilter();
        filter.setClientId(accountId);
        filter.setStatus(parseStatus(status));
        filter.setFrom(from);
        filter.setTo(to);
        return orderMapper.listByAccount(filter).stream().map(row -> toHistoryEntry(row)).toList();
    }

    /**
     * The shared existence, reachability and activeness check behind every read.
     */
    private AccountRow resolve(Long accountId, Long tokenAccountId) {
        AccountRow row = accountMapper.findRow(accountId)
                .orElseThrow(() -> new AccountNotFoundException(accountId));
        if (tokenAccountId != null && !tokenAccountId.equals(accountId)) {
            throw new AccountNotActiveException(accountId, "TOKEN");
        }
        Client client = toClient(row);
        if (!client.canTrade()) {
            throw new AccountNotActiveException(accountId, client.getAccountState());
        }
        return row;
    }

    /**
     * An unknown status value on the query string is invalid input, {@code VAL-422}.
     */
    private static OrderStatus parseStatus(String status) {
        if (status == null) {
            return null;
        }
        try {
            return OrderStatus.valueOf(status);
        } catch (IllegalArgumentException e) {
            throw new InvalidOrderException("status", status);
        }
    }

    private static Client toClient(AccountRow row) {
        return new Client(row.getClientId(), row.getAccountNumber(), row.getName(), row.getEmail(),
                row.getPhone(), row.getCreatedOn(), row.getAccountState(), row.getWalletBalance());
    }

    private static OrderHistoryEntry toHistoryEntry(OrderRow row) {
        return new OrderHistoryEntry(displayId(row.getOrderUuid()), row.getAccountId(), row.getSymbol(),
                row.getSide(), row.getQuantity(), row.getPrice(), row.getExecutedPrice(),
                row.getStatus(), row.getIdempotencyKey(), row.getCreatedAt());
    }

    private static String displayId(String orderUuid) {
        return "ORD-" + orderUuid;
    }
}