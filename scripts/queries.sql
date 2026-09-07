SELECT order_id, instrument_id, side, order_type, quantity, price,
       status, created_at
FROM orders
WHERE client_id = :client_id
  AND status = 'NEW'
ORDER BY created_at DESC, order_id DESC;

SELECT order_id, instrument_id, side, order_type, quantity, price,
       executed_price, status, created_at
FROM orders
WHERE client_id = :client_id
ORDER BY created_at DESC, order_id DESC
LIMIT 50;

SELECT 'HOLDING' AS book, i.instrument_id, i.instrument_name, h.quantity,
       h.price_per_unit, h.overall_gains
FROM portfolio_holding h
JOIN instruments i ON i.instrument_id = h.instrument_id
WHERE h.client_id = :client_id
  AND h.quantity <> 0
UNION ALL
SELECT 'POSITION' AS book, i.instrument_id, i.instrument_name, p.quantity,
       p.price_per_unit, p.overall_gains
FROM portfolio_positions p
JOIN instruments i ON i.instrument_id = p.instrument_id
WHERE p.client_id = :client_id
  AND p.quantity <> 0;

SELECT order_id, client_id, instrument_id, side, order_type, quantity,
       price, status, created_at
FROM orders
WHERE created_at > :since_timestamp
ORDER BY created_at ASC, order_id ASC;

SELECT client_id, name, email, account_state
FROM clients
WHERE account_number = :account_number_reference;

SELECT
    o.order_id,
    o.instrument_id,
    o.created_at,
    o.executed_price * o.quantity AS value,
    SUM(o.executed_price * o.quantity) OVER (
        ORDER BY o.created_at ASC, o.order_id ASC
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_cash_committed,
    RANK() OVER (
        PARTITION BY o.instrument_id
        ORDER BY o.executed_price * o.quantity DESC
    ) AS rank_within_instrument
FROM orders o
WHERE o.client_id = :client_id
  AND o.status = 'FILLED'
ORDER BY o.created_at ASC, o.order_id ASC;
