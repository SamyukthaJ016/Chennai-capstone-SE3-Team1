package com.team1.trading.api.service;

import com.team1.trading.api.dto.OrderResponse;
import com.team1.trading.api.mapper.AccountMapper;
import com.team1.trading.api.mapper.AccountMapper.AccountCashUpdate;
import com.team1.trading.api.mapper.AccountMapper.AccountRow;
import com.team1.trading.api.mapper.InstrumentMapper;
import com.team1.trading.api.mapper.InstrumentMapper.InstrumentRow;
import com.team1.trading.api.mapper.OrderMapper;
import com.team1.trading.api.mapper.OrderMapper.OrderInsert;
import com.team1.trading.api.mapper.OrderMapper.OrderRow;
import com.team1.trading.api.mapper.PositionMapper;
import com.team1.trading.api.mapper.PositionMapper.PositionRow;
import com.team1.trading.api.mapper.PositionMapper.PositionWrite;
import com.team1.trading.domain.dto.PlaceOrderRequest;
import com.team1.trading.domain.entity.Client;
import com.team1.trading.domain.entity.Instrument;
import com.team1.trading.domain.entity.Order;
import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.entity.types.OrderType;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.DuplicateOrderException;
import com.team1.trading.domain.exception.InsufficientFundsException;
import com.team1.trading.domain.exception.InsufficientHoldingsException;
import com.team1.trading.domain.exception.InstrumentNotFoundException;
import com.team1.trading.domain.exception.InvalidOrderException;
import com.team1.trading.domain.exception.OrderConflictException;
import com.team1.trading.domain.exception.OrderNotCancellableException;
import com.team1.trading.domain.exception.OrderNotFoundException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.UUID;

/**
 * Order placement and cancellation for contracts/trade-api.yaml.
 *
 * <p>The business rules are the domain's own behaviour and exceptions: the account and
 * instrument entities decide {@code canTrade}/{@code canAfford}/{@code isTradable}, and every
 * rejection is a {@code DomainException} from the shared jar. This service orders those checks
 * exactly as the contract's rule table does - first failure wins - and then files the order, the
 * cash change and the position update in one transaction.
 */
@Service
public class OrderService {

    private final AccountMapper accountMapper;
    private final InstrumentMapper instrumentMapper;
    private final OrderMapper orderMapper;
    private final PositionMapper positionMapper;

    public OrderService(AccountMapper accountMapper, InstrumentMapper instrumentMapper,
                        OrderMapper orderMapper, PositionMapper positionMapper) {
        this.accountMapper = accountMapper;
        this.instrumentMapper = instrumentMapper;
        this.orderMapper = orderMapper;
        this.positionMapper = positionMapper;
    }

    /**
     * Validates rules 1 to 8 in order, then fills synchronously: the order, the cash move and
     * the position change commit in one transaction (rules 9 and 10).
     *
     * <p>Rule 8 is enforced by the {@code uq_orders_idempotency_key} constraint, not by a read
     * then a write, so two concurrent requests with the same key cannot both pass a pre-check.
     */
    @Transactional
    public OrderResponse placeOrder(PlaceOrderRequest request, Long tokenAccountId) {
        Long accountId = request.getAccountId();

        AccountRow accountRow = accountMapper.findRow(accountId)
                .orElseThrow(() -> new AccountNotFoundException(accountId));          // rule 1
        if (tokenAccountId != null && !tokenAccountId.equals(accountId)) {
            throw new AccountNotActiveException(accountId, "TOKEN");
        }
        Client client = toClient(accountRow);
        if (!client.canTrade()) {                                                     // rule 2
            throw new AccountNotActiveException(accountId, client.getAccountState());
        }

        InstrumentRow instrumentRow = instrumentMapper.findRowBySymbol(request.getSymbol())
                .orElseThrow(() -> new InstrumentNotFoundException(request.getSymbol())); // rule 3
        Instrument instrument = new Instrument(instrumentRow.getInstrumentId(),
                instrumentRow.getInstrumentName(), instrumentRow.isActive(), instrumentRow.getUpdatedOn());
        if (!instrument.isTradable()) {
            throw new InstrumentNotFoundException(request.getSymbol());               // rule 3
        }

        Integer quantity = request.getQuantity();
        if (quantity == null || quantity <= 0) {                                      // rule 4
            throw new InvalidOrderException("quantity", quantity);
        }
        BigDecimal price = request.getPrice();
        if (price == null || price.signum() <= 0) {                                   // rule 5
            throw new InvalidOrderException("price", price);
        }

        BigDecimal cost = money(BigDecimal.valueOf(quantity).multiply(price));
        if (request.getSide() == OrderSide.BUY) {                                     // rule 6
            if (cost.compareTo(client.getWalletBalance()) > 0) {
                throw new InsufficientFundsException(accountId, cost, client.getWalletBalance());
            }
        } else {                                                                      // rule 7
            int heldQuantity = positionMapper.findHeld(accountId, request.getSymbol())
                    .map(PositionRow::getQuantity).orElse(0);
            if (heldQuantity < quantity) {
                throw new InsufficientHoldingsException(accountId, request.getSymbol(),
                        BigDecimal.valueOf(quantity), BigDecimal.valueOf(heldQuantity));
            }
        }

        String orderUuid = UUID.randomUUID().toString();
        Order order = new Order(accountId, accountId, request.getSymbol(), OrderType.POSITION,
                request.getSide(), BigDecimal.valueOf(quantity), price, request.getIdempotencyKey());
        order.markCompleted(price);                                                   // synchronous fill
        try {
            orderMapper.insert(toInsert(order, orderUuid));                           // rule 8
        } catch (DataIntegrityViolationException e) {
            if (isIdempotencyViolation(e)) {
                throw new DuplicateOrderException(request.getIdempotencyKey());
            }
            throw e;
        }

        BigDecimal newBalance = request.getSide() == OrderSide.BUY
                ? client.getWalletBalance().subtract(cost)
                : client.getWalletBalance().add(money(BigDecimal.valueOf(quantity).multiply(price)));
        int cashRows = accountMapper.updateCashGuarded(
                new AccountCashUpdate(accountId, newBalance, accountRow.getVersion()));
        if (cashRows == 0) {
            throw new OrderConflictException("account version changed concurrently");
        }

        PositionWrite position = new PositionWrite(accountId, request.getSymbol(), quantity, price);
        if (request.getSide() == OrderSide.BUY) {
            positionMapper.upsertBuy(position);
            positionMapper.upsertBuyHolding(position);
        } else {
            if (positionMapper.reduceSell(position) == 0
                    || positionMapper.reduceSellHolding(position) == 0) {
                throw new OrderConflictException("position changed concurrently");
            }
        }

        return new OrderResponse(displayId(orderUuid), OrderStatus.FILLED, "Order executed",
                request.getSymbol(), request.getSide(), quantity, price);
    }

    /**
     * Cancels a {@code NEW} order with a guarded state transition inside the database. The
     * {@code WHERE status = 'NEW'} update races nothing: it is the whole transition, not a read
     * followed by a write.
     */
    @Transactional
    public OrderResponse cancel(String orderUuid, Long tokenAccountId) {
        OrderRow row = orderMapper.findByUuid(orderUuid)
                .orElseThrow(() -> new OrderNotFoundException(displayId(orderUuid)));
        if (tokenAccountId != null && !tokenAccountId.equals(row.getAccountId())) {
            throw new AccountNotActiveException(row.getAccountId(), "TOKEN");
        }
        if (orderMapper.markCancelled(orderUuid) == 0) {
            throw new OrderNotCancellableException(displayId(orderUuid), row.getStatus().name());
        }
        return new OrderResponse(displayId(orderUuid), OrderStatus.CANCELLED, "Order cancelled",
                row.getSymbol(), row.getSide(), row.getQuantity(), row.getPrice());
    }

    private static Client toClient(AccountRow row) {
        return new Client(row.getClientId(), row.getAccountNumber(), row.getName(), row.getEmail(),
                row.getPhone(), row.getCreatedOn(), row.getAccountState(), row.getWalletBalance());
    }

    private static OrderInsert toInsert(Order order, String orderUuid) {
        OrderInsert insert = new OrderInsert();
        insert.setClientId(order.getClientId());
        insert.setAccountId(order.getAccountId());
        insert.setInstrumentId(order.getInstrumentId());
        insert.setOrderType(order.getOrderType().name());
        insert.setSide(order.getSide());
        insert.setQuantity(order.getQuantity().intValue());
        insert.setPrice(order.getPrice());
        insert.setExecutedPrice(order.getExecutedPrice());
        insert.setStatus(order.getStatus().name());
        insert.setIdempotencyKey(order.getIdempotencyKey());
        insert.setExternalOrderId(order.getExternalOrderId());
        insert.setOrderUuid(orderUuid);
        return insert;
    }

    private static String displayId(String orderUuid) {
        return "ORD-" + orderUuid;
    }

    private static BigDecimal money(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_UP);
    }

    private static boolean isIdempotencyViolation(DataIntegrityViolationException e) {
        String detail = String.valueOf(e.getMostSpecificCause().getMessage());
        return detail.contains("uq_orders_idempotency_key") || detail.toLowerCase().contains("idempotency");
    }
}