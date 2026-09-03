package com.team1.trading.domain.service;

import com.team1.trading.domain.dto.OrderSide;
import com.team1.trading.domain.dto.PlaceOrderRequest;
import com.team1.trading.domain.entity.Client;
import com.team1.trading.domain.entity.Instrument;
import com.team1.trading.domain.entity.Order;
import com.team1.trading.domain.entity.PortfolioHolding;
import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.DomainException;
import com.team1.trading.domain.exception.DuplicateOrderException;
import com.team1.trading.domain.exception.InstrumentNotFoundException;
import com.team1.trading.domain.exception.InsufficientFundsException;
import com.team1.trading.domain.exception.InsufficientHoldingsException;
import com.team1.trading.domain.exception.InvalidOrderException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Business rules 1 to 8, each one firing and each one not firing, plus the
 * evaluation order itself.
 */
class OrderLogicTest {

    private static final long ACCOUNT_ID = 1L;
    private static final String SYMBOL = "ACME";
    private static final String KEY = "6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e";

    private Map<Long, Client> accounts;
    private Map<String, Instrument> instruments;
    private List<PortfolioHolding> holdings;
    private OrdersService orders;
    private PortfolioService service;

    @BeforeEach
    void setUp() {
        accounts = new HashMap<>();
        instruments = new HashMap<>();
        holdings = new ArrayList<>();
        orders = new OrdersService();
        service = new PortfolioService(accounts, instruments, holdings, orders);
    }

    private Client account(long accountId, String balance, String state) {
        Client client = new Client(accountId, (int) accountId, "Holder " + accountId,
                "holder" + accountId + "@example.com", "900000000" + accountId);
        client.credit(new BigDecimal(balance));
        if ("SUSPENDED".equals(state)) {
            client.suspend();
        } else if ("INACTIVE".equals(state)) {
            client.deactivate();
        }
        accounts.put(accountId, client);
        return client;
    }

    private Client activeAccount(String balance) {
        return account(ACCOUNT_ID, balance, "ACTIVE");
    }

    private void tradable(String symbol) {
        instruments.put(symbol, new Instrument(symbol, symbol + " Corporation"));
    }

    private void delisted(String symbol) {
        instruments.put(symbol, new Instrument(symbol, symbol + " Corporation", false, LocalDateTime.now()));
    }

    private void holding(Client owner, String symbol, int quantity) {
        holdings.add(new PortfolioHolding(1L, owner.getClientId(), symbol, quantity, new BigDecimal("10.00")));
    }

    private PlaceOrderRequest buy(int quantity, String price) {
        return new PlaceOrderRequest(ACCOUNT_ID, SYMBOL, OrderSide.BUY, quantity, new BigDecimal(price), KEY);
    }

    private PlaceOrderRequest sell(int quantity, String price) {
        return new PlaceOrderRequest(ACCOUNT_ID, SYMBOL, OrderSide.SELL, quantity, new BigDecimal(price), KEY);
    }

    // ---------- rule 1 : the account must exist : ACC-404 ----------

    @Nested
    @DisplayName("Rule 1 - the account must exist")
    class Rule1Tests {

        @Test
        @DisplayName("Fires when no account carries the key on the request")
        void fires_whenAccountMissing() {
            tradable(SYMBOL);

            AccountNotFoundException thrown = assertThrows(AccountNotFoundException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("ACC-404", thrown.getCode());
        }

        @Test
        @DisplayName("Does not fire when the account exists")
        void doesNotFire_whenAccountExists() {
            activeAccount("1000.00");
            tradable(SYMBOL);

            assertDoesNotThrow(() -> service.placeOrder(buy(10, "5.00")));
        }
    }

    // ---------- rule 2 : the account must be ACTIVE : ACC-403 ----------

    @Nested
    @DisplayName("Rule 2 - the account must be ACTIVE")
    class Rule2Tests {

        @Test
        @DisplayName("Fires when the account is SUSPENDED")
        void fires_whenAccountSuspended() {
            account(ACCOUNT_ID, "1000.00", "SUSPENDED");
            tradable(SYMBOL);

            AccountNotActiveException thrown = assertThrows(AccountNotActiveException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("ACC-403", thrown.getCode());
        }

        @Test
        @DisplayName("Fires when the account is INACTIVE")
        void fires_whenAccountInactive() {
            account(ACCOUNT_ID, "1000.00", "INACTIVE");
            tradable(SYMBOL);

            assertThrows(AccountNotActiveException.class,
                    () -> service.placeOrder(buy(10, "5.00")));
        }

        @Test
        @DisplayName("Does not fire when the account is ACTIVE")
        void doesNotFire_whenAccountActive() {
            activeAccount("1000.00");
            tradable(SYMBOL);

            assertDoesNotThrow(() -> service.placeOrder(buy(10, "5.00")));
        }
    }

    // ---------- rule 3 : the instrument must exist and be tradable : INS-404 ----------

    @Nested
    @DisplayName("Rule 3 - the instrument must exist and be tradable")
    class Rule3Tests {

        @Test
        @DisplayName("Fires when the symbol is unknown")
        void fires_whenSymbolUnknown() {
            activeAccount("1000.00");

            InstrumentNotFoundException thrown = assertThrows(InstrumentNotFoundException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("INS-404", thrown.getCode());
        }

        @Test
        @DisplayName("Fires when the instrument is known but delisted")
        void fires_whenInstrumentDelisted() {
            activeAccount("1000.00");
            delisted(SYMBOL);

            InstrumentNotFoundException thrown = assertThrows(InstrumentNotFoundException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("INS-404", thrown.getCode());
        }

        @Test
        @DisplayName("Does not fire when the instrument exists and is tradable")
        void doesNotFire_whenInstrumentTradable() {
            activeAccount("1000.00");
            tradable(SYMBOL);

            assertDoesNotThrow(() -> service.placeOrder(buy(10, "5.00")));
        }
    }

    // ---------- rule 4 : quantity greater than zero : VAL-422 ----------

    @Nested
    @DisplayName("Rule 4 - quantity must be greater than zero")
    class Rule4Tests {

        @BeforeEach
        void world() {
            activeAccount("1000.00");
            tradable(SYMBOL);
        }

        @Test
        @DisplayName("Fires when quantity is zero")
        void fires_whenQuantityZero() {
            InvalidOrderException thrown = assertThrows(InvalidOrderException.class,
                    () -> service.placeOrder(buy(0, "5.00")));

            assertEquals("VAL-422", thrown.getCode());
        }

        @Test
        @DisplayName("Fires when quantity is negative")
        void fires_whenQuantityNegative() {
            assertThrows(InvalidOrderException.class,
                    () -> service.placeOrder(buy(-1, "5.00")));
        }

        @Test
        @DisplayName("Fires when quantity is absent, because a replaying caller never ran a validator")
        void fires_whenQuantityNull() {
            PlaceOrderRequest request = buy(10, "5.00");
            request.setQuantity(null);

            assertThrows(InvalidOrderException.class, () -> service.placeOrder(request));
        }

        @Test
        @DisplayName("Does not fire when quantity is one, the smallest legal quantity")
        void doesNotFire_whenQuantityIsOne() {
            assertDoesNotThrow(() -> service.placeOrder(buy(1, "5.00")));
        }
    }

    // ---------- rule 5 : price greater than zero : VAL-422 ----------

    @Nested
    @DisplayName("Rule 5 - price must be greater than zero")
    class Rule5Tests {

        @BeforeEach
        void world() {
            activeAccount("1000.00");
            tradable(SYMBOL);
        }

        @Test
        @DisplayName("Fires when price is zero")
        void fires_whenPriceZero() {
            InvalidOrderException thrown = assertThrows(InvalidOrderException.class,
                    () -> service.placeOrder(buy(10, "0.00")));

            assertEquals("VAL-422", thrown.getCode());
        }

        @Test
        @DisplayName("Fires when price is negative")
        void fires_whenPriceNegative() {
            assertThrows(InvalidOrderException.class,
                    () -> service.placeOrder(buy(10, "-0.01")));
        }

        @Test
        @DisplayName("Fires when price is absent")
        void fires_whenPriceNull() {
            PlaceOrderRequest request = buy(10, "5.00");
            request.setPrice(null);

            assertThrows(InvalidOrderException.class, () -> service.placeOrder(request));
        }

        @Test
        @DisplayName("Does not fire when price is one penny, the smallest legal price")
        void doesNotFire_whenPriceIsOnePenny() {
            assertDoesNotThrow(() -> service.placeOrder(buy(10, "0.01")));
        }
    }

    // ---------- rule 6 : a BUY needs the cash : ORD-400 ----------

    @Nested
    @DisplayName("Rule 6 - on a BUY the balance must cover quantity times price")
    class Rule6Tests {

        @Test
        @DisplayName("Fires when the cost is one penny above the balance")
        void fires_whenCostExceedsBalance() {
            activeAccount("49.99");
            tradable(SYMBOL);

            InsufficientFundsException thrown = assertThrows(InsufficientFundsException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("ORD-400", thrown.getCode());
        }

        @Test
        @DisplayName("Does not fire when the balance exactly covers the cost")
        void doesNotFire_whenBalanceExactlyCoversCost() {
            activeAccount("50.00");
            tradable(SYMBOL);

            assertDoesNotThrow(() -> service.placeOrder(buy(10, "5.00")));
        }

        @Test
        @DisplayName("Does not fire on a SELL, however empty the account is")
        void doesNotFire_onSell() {
            Client owner = activeAccount("0.00");
            tradable(SYMBOL);
            holding(owner, SYMBOL, 10);

            assertDoesNotThrow(() -> service.placeOrder(sell(10, "5.00")));
        }
    }

    // ---------- rule 7 : a SELL needs the holding : ORD-409 ----------

    @Nested
    @DisplayName("Rule 7 - on a SELL the held quantity must cover the order")
    class Rule7Tests {

        @Test
        @DisplayName("Fires when the sell is larger than the holding")
        void fires_whenSellExceedsHolding() {
            Client owner = activeAccount("1000.00");
            tradable(SYMBOL);
            holding(owner, SYMBOL, 9);

            InsufficientHoldingsException thrown = assertThrows(InsufficientHoldingsException.class,
                    () -> service.placeOrder(sell(10, "5.00")));

            assertEquals("ORD-409", thrown.getCode());
        }

        @Test
        @DisplayName("Fires when there is no holding in that instrument at all")
        void fires_whenNoHoldingAtAll() {
            activeAccount("1000.00");
            tradable(SYMBOL);

            assertThrows(InsufficientHoldingsException.class,
                    () -> service.placeOrder(sell(10, "5.00")));
        }

        @Test
        @DisplayName("Does not fire when the holding exactly covers the quantity")
        void doesNotFire_whenHoldingExactlyCovers() {
            Client owner = activeAccount("1000.00");
            tradable(SYMBOL);
            holding(owner, SYMBOL, 10);

            assertDoesNotThrow(() -> service.placeOrder(sell(10, "5.00")));
        }

        @Test
        @DisplayName("Does not fire on a BUY, however empty the portfolio is")
        void doesNotFire_onBuy() {
            activeAccount("1000.00");
            tradable(SYMBOL);

            assertDoesNotThrow(() -> service.placeOrder(buy(10, "5.00")));
        }
    }

    // ---------- rule 8 : the idempotency key : ORD-409 ----------

    @Nested
    @DisplayName("Rule 8 - the idempotency key must not already have been used")
    class Rule8Tests {

        @BeforeEach
        void world() {
            activeAccount("1000.00");
            tradable(SYMBOL);
        }

        @Test
        @DisplayName("Fires when the same key is presented a second time")
        void fires_whenKeyAlreadyUsed() {
            service.placeOrder(buy(10, "5.00"));

            DuplicateOrderException thrown = assertThrows(DuplicateOrderException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("ORD-409", thrown.getCode());
        }

        @Test
        @DisplayName("Does not fire the first time a key is used")
        void doesNotFire_onFirstUse() {
            assertDoesNotThrow(() -> service.placeOrder(buy(10, "5.00")));
        }

        @Test
        @DisplayName("Does not fire for two orders carrying different keys")
        void doesNotFire_forDifferentKeys() {
            service.placeOrder(buy(10, "5.00"));

            PlaceOrderRequest second = buy(10, "5.00");
            second.setIdempotencyKey("a-different-key-0000000002");

            assertDoesNotThrow(() -> service.placeOrder(second));
        }

        @Test
        @DisplayName("The key is claimed rather than read, so only one of two claims wins")
        void claimIsAtomic_onlyOneClaimWins() {
            assertTrue(orders.claimIdempotencyKey("some-fresh-key-0001"));

            assertTrue(!orders.claimIdempotencyKey("some-fresh-key-0001"),
                    "a key already claimed must not be claimable a second time");
        }
    }

    // ---------- the evaluation order itself ----------

    @Nested
    @DisplayName("Evaluation order - the first failure wins")
    class EvaluationOrderTests {

        @Test
        @DisplayName("A missing account beats an unknown instrument, so ACC-404 not INS-404")
        void rule1_beatsRule3() {
            DomainException thrown = assertThrows(AccountNotFoundException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("ACC-404", thrown.getCode());
        }

        @Test
        @DisplayName("A suspended account holding no cash gets ACC-403 rather than ORD-400")
        void rule2_beatsRule6() {
            account(ACCOUNT_ID, "0.00", "SUSPENDED");
            tradable(SYMBOL);

            DomainException thrown = assertThrows(AccountNotActiveException.class,
                    () -> service.placeOrder(buy(10, "5.00")));

            assertEquals("ACC-403", thrown.getCode());
        }

        @Test
        @DisplayName("A suspended account beats an unknown instrument, so ACC-403 not INS-404")
        void rule2_beatsRule3() {
            account(ACCOUNT_ID, "1000.00", "SUSPENDED");

            assertThrows(AccountNotActiveException.class,
                    () -> service.placeOrder(buy(10, "5.00")));
        }

        @Test
        @DisplayName("An unknown instrument beats a zero quantity, so INS-404 not VAL-422")
        void rule3_beatsRule4() {
            activeAccount("1000.00");

            assertThrows(InstrumentNotFoundException.class,
                    () -> service.placeOrder(buy(0, "5.00")));
        }

        @Test
        @DisplayName("A zero quantity is reported before a zero price, so rule 4 beats rule 5")
        void rule4_beatsRule5() {
            activeAccount("1000.00");
            tradable(SYMBOL);

            InvalidOrderException thrown = assertThrows(InvalidOrderException.class,
                    () -> service.placeOrder(buy(0, "0.00")));

            assertEquals("VAL-422", thrown.getCode());
        }

        @Test
        @DisplayName("A zero price beats an unaffordable order, so VAL-422 not ORD-400")
        void rule5_beatsRule6() {
            activeAccount("0.00");
            tradable(SYMBOL);

            assertThrows(InvalidOrderException.class,
                    () -> service.placeOrder(buy(10, "0.00")));
        }

        @Test
        @DisplayName("Insufficient funds beats a duplicate key, so ORD-400 not ORD-409")
        void rule6_beatsRule8() {
            activeAccount("1000.00");
            tradable(SYMBOL);
            service.placeOrder(buy(10, "5.00"));

            assertThrows(InsufficientFundsException.class,
                    () -> service.placeOrder(buy(1000000, "5.00")));
        }

        @Test
        @DisplayName("Insufficient holdings beats a duplicate key, so rule 7 is raised and not rule 8")
        void rule7_beatsRule8() {
            Client owner = activeAccount("1000.00");
            tradable(SYMBOL);
            holding(owner, SYMBOL, 10);
            service.placeOrder(sell(10, "5.00"));

            assertThrows(InsufficientHoldingsException.class,
                    () -> service.placeOrder(sell(1000, "5.00")));
        }
    }

    // ---------- what an accepted order looks like ----------

    @Nested
    @DisplayName("An order that passes all eight rules")
    class AcceptedOrderTests {

        @BeforeEach
        void world() {
            activeAccount("1000.00");
            tradable(SYMBOL);
        }

        @Test
        @DisplayName("Is returned in status NEW")
        void acceptedOrder_isNew() {
            Order order = service.placeOrder(buy(10, "5.00"));

            assertEquals(OrderStatus.NEW, order.getStatus());
        }

        @Test
        @DisplayName("Carries the account, the symbol and the idempotency key it was placed with")
        void acceptedOrder_carriesTheRequestValues() {
            Order order = service.placeOrder(buy(10, "5.00"));

            assertNotNull(order);
            assertEquals(ACCOUNT_ID, order.getAccountId());
            assertEquals(SYMBOL, order.getInstrumentId());
            assertEquals(KEY, order.getIdempotencyKey());
        }

        @Test
        @DisplayName("Has claimed its idempotency key, so the same key cannot be claimed again")
        void acceptedOrder_hasClaimedItsKey() {
            service.placeOrder(buy(10, "5.00"));

            assertTrue(!orders.claimIdempotencyKey(KEY));
        }
    }
}
