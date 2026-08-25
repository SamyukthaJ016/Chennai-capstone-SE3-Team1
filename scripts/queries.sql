-- Query 1: All open orders for one account, newest first
SELECT order_id, instrument_id, type, product_type, quantity, price_per_unit,
       status, order_timestamp
FROM orders
WHERE client_id = :client_id
  AND status IN ('RECEIVED', 'IN_PROGRESS')
ORDER BY order_timestamp DESC, order_id DESC;

-- Query 2: The last 50 orders for one account in any state, newest first
SELECT order_id, instrument_id, type, product_type, quantity, price_per_unit,
       status, order_timestamp
FROM orders
WHERE client_id = :client_id
ORDER BY order_timestamp DESC, order_id DESC
LIMIT 50;

-- Query 3: Everything one account currently holds, with quantity and average cost
SELECT 'DELIVERY' AS book, i.instrument_name, h.quantity, h.avg_price
FROM portfolio_holding h
JOIN instruments i ON i.instrument_id = h.instrument_id
WHERE h.client_id = :client_id
  AND h.quantity <> 0
UNION ALL
SELECT 'INTRADAY' AS book, i.instrument_name, p.quantity, p.avg_price
FROM portfolio_positions p
JOIN instruments i ON i.instrument_id = p.instrument_id
WHERE p.client_id = :client_id
  AND p.quantity <> 0;

-- Query 4: Every order created since a given timestamp, across all accounts
SELECT order_id, client_id, instrument_id, type, product_type, quantity,
       price_per_unit, status, order_timestamp
FROM orders
WHERE order_timestamp > :since_timestamp
ORDER BY order_timestamp ASC, order_id ASC;

-- Query 5: Resolve an account from the customer-facing reference quoted on a call
SELECT client_id, name, email, status
FROM clients
WHERE account_number = :account_number_reference;

-- Query 6: For one account, every filled order oldest first, each with the
-- running total of cash committed to date and its rank by value within its instrument
SELECT
    o.order_id,
    o.instrument_id,
    o.order_timestamp,
    ts.value,
    SUM(ts.value) OVER (
        ORDER BY o.order_timestamp ASC, o.order_id ASC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_cash_committed,
    RANK() OVER (
        PARTITION BY o.instrument_id
        ORDER BY ts.value DESC
    ) AS rank_within_instrument
FROM orders o
JOIN transaction_success ts ON ts.order_id = o.order_id
WHERE o.client_id = :client_id
ORDER BY o.order_timestamp ASC, o.order_id ASC;
