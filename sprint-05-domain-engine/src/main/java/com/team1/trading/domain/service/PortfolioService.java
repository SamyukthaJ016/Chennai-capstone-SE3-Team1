package com.team1.trading.domain.service;

import com.team1.trading.domain.dto.OrderSide;
import com.team1.trading.domain.dto.PlaceOrderRequest;
import com.team1.trading.domain.entity.Client;
import com.team1.trading.domain.entity.Instrument;
import com.team1.trading.domain.entity.Order;
import com.team1.trading.domain.entity.PortfolioHolding;
import com.team1.trading.domain.entity.types.OrderType;
import com.team1.trading.domain.entity.types.TransactionType;
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
 * They are enforced in this order and the first failure wins, because the
 * order is part of the contract: a request that breaks two rules receives the
 * code of the first, and a suspended account holding no cash gets ACC-403
 * rather than ORD-400.
 *
 *   1  the account must exist                             ACC-404
 *   2  the account must be ACTIVE                         ACC-403
 *   3  the instrument must exist and be tradable          INS-404
 *   4  quantity must be greater than zero                 VAL-422
 *   5  price must be greater than zero                    VAL-422
 *   6  on a BUY, the balance must cover quantity x price  ORD-400
 *   7  on a SELL, the holding must cover the quantity     ORD-409
 *   8  the idempotency key must not already be used       ORD-409
 *
 * Why that order. The identity questions come first because there is no point
 * pricing an order for an account that cannot trade, and because they narrow
 * what the later rules may read: rule 6 needs the balance of an account rule 1
 * has already found. Validation sits at 4 and 5 because a quantity of zero
 * would make rules 6 and 7 pass trivially. Rule 8 is last because it is the
 * only rule that writes anything, and claiming a key for an order the first
 * seven rules were going to refuse would burn it.
 *
 * Nothing here knows about HTTP, a database or a framework. Placement records
 * the order in status NEW and moves no money: cash and the holding move
 * together when the trade settles, which is not this method.
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

        // Rule 2. The account must be ACTIVE. Suspended and inactive both stop here,
        // which is why a suspended account with no cash gets ACC-403 and not ORD-400.
        if (!account.canTrade()) {
            throw new AccountNotActiveException(accountId, account.getAccountState());
        }

        // Rule 3. The instrument must exist and still be tradable. A delisted symbol
        // answers exactly as an unknown one does.
        String symbol = request.getSymbol();
        Instrument instrument = symbol == null ? null : instruments.get(symbol);
        if (instrument == null || !instrument.isTradable()) {
            throw new InstrumentNotFoundException(symbol);
        }

        // Rule 4. Quantity greater than zero. Checked here as well as on the DTO,
        // because a caller that replays an order never runs a validator.
        Integer quantity = request.getQuantity();
        if (quantity == null || quantity <= 0) {
            throw new InvalidOrderException("quantity", quantity);
        }

        // Rule 5. Price greater than zero, for the same reason.
        BigDecimal price = request.getPrice();
        if (price == null || price.signum() <= 0) {
            throw new InvalidOrderException("price", price);
        }

        // A side is required before rules 6 and 7 can know which of them applies.
        OrderSide side = request.getSide();
        if (side == null) {
            throw new InvalidOrderException("side", null);
        }

        BigDecimal orderQuantity = BigDecimal.valueOf(quantity);
        BigDecimal cost = orderQuantity.multiply(price).setScale(MONEY_SCALE, RoundingMode.HALF_UP);

        // Rule 6. On a BUY the balance must cover quantity times price. The account
        // answers the question; nothing is subtracted to find out.
        if (side == OrderSide.BUY && !account.canAfford(cost)) {
            throw new InsufficientFundsException(accountId, cost, account.getWalletBalance());
        }

        // Rule 7. On a SELL the held quantity must be at least the order quantity.
        // No holding and a holding of zero mean the same thing here.
        if (side == OrderSide.SELL) {
            BigDecimal held = heldQuantity(account, symbol);
            if (held.compareTo(orderQuantity) < 0) {
                throw new InsufficientHoldingsException(accountId, symbol, orderQuantity, held);
            }
        }

        // Rule 8. The idempotency key must not already have been used. A claim, not
        // a read, so two concurrent requests carrying one key produce one order and
        // one ORD-409.
        String idempotencyKey = request.getIdempotencyKey();
        if (!orders.claimIdempotencyKey(idempotencyKey)) {
            throw new DuplicateOrderException(idempotencyKey);
        }

        return new Order(account.getUserId(), accountId, instrument.getInstrumentId(),
                DEFAULT_ORDER_TYPE, transactionType(side), orderQuantity, price, idempotencyKey);
    }

    /** What the account holds in one symbol, zero when it holds none. */
    private BigDecimal heldQuantity(Client account, String symbol) {
        BigDecimal total = BigDecimal.ZERO;
        for (PortfolioHolding holding : holdings) {
            if (account.getClientId().equals(holding.getClientId())
                    && symbol.equals(holding.getInstrumentId())) {
                total = total.add(BigDecimal.valueOf(holding.getQuantity()));
            }
        }
        return total;
    }

    /** The request carries a side; the order stores it as its transaction type. */
    private static TransactionType transactionType(OrderSide side) {
        return side == OrderSide.BUY ? TransactionType.BUY : TransactionType.SELL;
    }

    private static final int MONEY_SCALE = 2;

    /**
     * The request has no order type of its own, so placement records the
     * delivery kind. Change this the day PlaceOrderRequest carries one.
     */
    private static final OrderType DEFAULT_ORDER_TYPE = OrderType.HOLDING;
}
