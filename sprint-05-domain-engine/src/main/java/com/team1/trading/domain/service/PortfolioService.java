package com.team1.trading.domain.service;

import com.team1.trading.domain.dto.PlaceOrderRequest;
import com.team1.trading.domain.entity.Client;
import com.team1.trading.domain.entity.Instrument;
import com.team1.trading.domain.entity.Order;
import com.team1.trading.domain.entity.PortfolioHolding;
import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderType;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.DuplicateOrderException;
import com.team1.trading.domain.exception.InstrumentNotFoundException;
import com.team1.trading.domain.exception.InsufficientFundsException;
import com.team1.trading.domain.exception.InsufficientHoldingsException;
import com.team1.trading.domain.exception.InvalidOrderException;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;

public class PortfolioService {

    private final Map<Long, Client> accounts;
    private final Map<String, Instrument> instruments;
    private final List<PortfolioHolding> holdings;
    private final OrdersService orders;

    public PortfolioService(Map<Long, Client> accounts, Map<String, Instrument> instruments,
                            List<PortfolioHolding> holdings, OrdersService orders) {
        this.accounts = accounts;
        this.instruments = instruments;
        this.holdings = holdings;
        this.orders = orders;
    }

    public Order placeOrder(PlaceOrderRequest request) {
        if (request == null) {
            throw new InvalidOrderException("request", null);
        }

        Long accountId = request.getAccountId();

        Client account = accountId == null ? null : accounts.get(accountId);
        if (account == null) {
            throw new AccountNotFoundException(accountId);
        }

        if (!account.canTrade()) {
            throw new AccountNotActiveException(accountId, account.getAccountState());
        }

        String symbol = request.getSymbol();
        Instrument instrument = symbol == null ? null : instruments.get(symbol);
        if (instrument == null || !instrument.isTradable()) {
            throw new InstrumentNotFoundException(symbol);
        }

        Integer quantity = request.getQuantity();
        if (quantity == null || quantity <= 0) {
            throw new InvalidOrderException("quantity", quantity);
        }

        BigDecimal price = request.getPrice();
        if (price == null || price.signum() <= 0) {
            throw new InvalidOrderException("price", price);
        }

        OrderSide side = request.getSide();
        if (side == null) {
            throw new InvalidOrderException("side", null);
        }

        BigDecimal orderQuantity = BigDecimal.valueOf(quantity);
        BigDecimal cost = orderQuantity.multiply(price).setScale(MONEY_SCALE, RoundingMode.HALF_UP);

        if (side == OrderSide.BUY && !account.canAfford(cost)) {
            throw new InsufficientFundsException(accountId, cost, account.getWalletBalance());
        }

        if (side == OrderSide.SELL) {
            BigDecimal held = heldQuantity(account, symbol);
            if (held.compareTo(orderQuantity) < 0) {
                throw new InsufficientHoldingsException(accountId, symbol, orderQuantity, held);
            }
        }

        String idempotencyKey = request.getIdempotencyKey();
        if (!orders.claimIdempotencyKey(idempotencyKey)) {
            throw new DuplicateOrderException(idempotencyKey);
        }

        return new Order(
                account.getClientId(),
                accountId,
                instrument.getInstrumentId(),
                DEFAULT_ORDER_TYPE,
                side,
                orderQuantity,
                price,
                idempotencyKey
        );
    }

    private BigDecimal heldQuantity(Client account, String symbol) {
        BigDecimal total = BigDecimal.ZERO;
        if (holdings == null || symbol == null) {
            return total;
        }
        for (PortfolioHolding holding : holdings) {
            if (account.getClientId().equals(holding.getUserId())
                    && symbol.equals(holding.getInstrumentId())) {
                total = total.add(BigDecimal.valueOf(holding.getQuantity()));
            }
        }
        return total;
    }

    private static final int MONEY_SCALE = 2;
    private static final OrderType DEFAULT_ORDER_TYPE = OrderType.HOLDING;
}
