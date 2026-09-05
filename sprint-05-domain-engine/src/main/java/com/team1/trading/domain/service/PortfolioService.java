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

/**
 * Business rules 1 to 8, in the domain rather than in a caller.
 *
 * Enforced in order (first failure wins):
 *   1  The account must exist                            ACC-404
 *   2  The account must be ACTIVE                        ACC-403
 *   3  The instrument must exist and be tradable         INS-404
 *   4  Quantity must be greater than zero                VAL-422
 *   5  Price must be greater than zero                   VAL-422
 *   6  On a BUY, the balance must cover quantity x price ORD-400
 *   7  On a SELL, the holding must cover the quantity    ORD-409
 *   8  The idempotency key must not already be used      ORD-409
 */
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

    /**
     * Evaluates the eight rules against the request and records the order.
     *
     * @return the accepted order, in status NEW.
     * @throws AccountNotFoundException      rule 1, ACC-404
     * @throws AccountNotActiveException     rule 2, ACC-403
     * @throws InstrumentNotFoundException   rule 3, INS-404
     * @throws InvalidOrderException         rules 4 and 5, VAL-422
     * @throws InsufficientFundsException    rule 6, ORD-400
     * @throws InsufficientHoldingsException rule 7, ORD-409
     * @throws DuplicateOrderException       rule 8, ORD-409
     */
    public Order placeOrder(PlaceOrderRequest request) {
        if (request == null) {
            throw new InvalidOrderException("request", null);
        }

        Long accountId = request.getAccountId();

        // Rule 1. The account must exist.
        Client account = accountId == null ? null : accounts.get(accountId);
        if (account == null) {
            throw new AccountNotFoundException(accountId);
        }

        // Rule 2. The account must be ACTIVE.
        if (!account.canTrade()) {
            throw new AccountNotActiveException(accountId, account.getAccountState());
        }

        // Rule 3. The instrument must exist and be tradable.
        String symbol = request.getSymbol();
        Instrument instrument = symbol == null ? null : instruments.get(symbol);
        if (instrument == null || !instrument.isTradable()) {
            throw new InstrumentNotFoundException(symbol);
        }

        // Rule 4. Quantity greater than zero.
        Integer quantity = request.getQuantity();
        if (quantity == null || quantity <= 0) {
            throw new InvalidOrderException("quantity", quantity);
        }

        // Rule 5. Price greater than zero.
        BigDecimal price = request.getPrice();
        if (price == null || price.signum() <= 0) {
            throw new InvalidOrderException("price", price);
        }

        // Side validation
        OrderSide side = request.getSide();
        if (side == null) {
            throw new InvalidOrderException("side", null);
        }

        BigDecimal orderQuantity = BigDecimal.valueOf(quantity);
        BigDecimal cost = orderQuantity.multiply(price).setScale(MONEY_SCALE, RoundingMode.HALF_UP);

        // Rule 6. On a BUY, the balance must cover quantity x price.
        if (side == OrderSide.BUY && !account.canAfford(cost)) {
            throw new InsufficientFundsException(accountId, cost, account.getWalletBalance());
        }

        // Rule 7. On a SELL, the held quantity must cover the order quantity.
        if (side == OrderSide.SELL) {
            BigDecimal held = heldQuantity(account, symbol);
            if (held.compareTo(orderQuantity) < 0) {
                throw new InsufficientHoldingsException(accountId, symbol, orderQuantity, held);
            }
        }

        // Rule 8. The idempotency key must not already have been used.
        String idempotencyKey = request.getIdempotencyKey();
        if (!orders.claimIdempotencyKey(idempotencyKey)) {
            throw new DuplicateOrderException(idempotencyKey);
        }

        return new Order(
                account.getClientId(),           // userId (Long)
                accountId,                       // accountId (Long)
                instrument.getInstrumentId(),    // instrumentId (String symbol)
                DEFAULT_ORDER_TYPE,              // orderType (OrderType)
                side,                            // side (OrderSide)
                orderQuantity,                   // quantity (BigDecimal)
                price,                           // price (BigDecimal)
                idempotencyKey                   // idempotencyKey (String)
        );
    }

    /** What the account holds in one symbol, zero when it holds none. */
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