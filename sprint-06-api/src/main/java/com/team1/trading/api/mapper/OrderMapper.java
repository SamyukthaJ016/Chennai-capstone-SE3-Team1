package com.team1.trading.api.mapper;

import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/**
 * SQL for the orders table, the audit trail. Every statement is fully parameterised with
 * {@code #{} binds; nothing is concatenated into these strings.
 *
 * <p>The cancellation is a guarded transition inside the database, exactly as
 * contracts/trade-api.yaml demands: the status is not read and then updated in two statements,
 * the {@code WHERE status = 'NEW'} guard makes the transition atomic against the executor.
 */
@Mapper
public interface OrderMapper {

    @Insert("""
            INSERT INTO orders (client_id, account_id, instrument_id, order_type, side, quantity,
                                price, executed_price, status, idempotency_key, external_order_id,
                                order_uuid, created_at, updated_at)
            VALUES (#{order.clientId}, #{order.accountId}, #{order.instrumentId}, #{order.orderType},
                    #{order.side}, #{order.quantity}, #{order.price}, #{order.executedPrice},
                    #{order.status}, #{order.idempotencyKey}, #{order.externalOrderId},
                    #{order.orderUuid}, now(), now())
            """)
    int insert(OrderInsert order);

    @Select("""
            SELECT order_uuid AS orderUuid, client_id AS clientId, account_id AS accountId,
                   instrument_id AS symbol, side, quantity, price, executed_price AS executedPrice,
                   status, idempotency_key AS idempotencyKey, created_at AS createdAt
            FROM orders
            WHERE order_uuid = #{orderUuid}
            """)
    Optional<OrderRow> findByUuid(@Param("orderUuid") String orderUuid);

    @Update("""
            UPDATE orders
            SET status     = 'CANCELLED',
                updated_at = now()
            WHERE order_uuid = #{orderUuid}
              AND status     = 'NEW'
            """)
    int markCancelled(@Param("orderUuid") String orderUuid);

    @Select("""
            SELECT order_uuid AS orderUuid, client_id AS clientId, account_id AS accountId,
                   instrument_id AS symbol, side, quantity, price, executed_price AS executedPrice,
                   status, idempotency_key AS idempotencyKey, created_at AS createdAt
            FROM orders
            WHERE client_id = #{filter.clientId}
              AND (   #{filter.status} IS NULL
                   OR status = #{filter.status})
              AND (   #{filter.from} IS NULL
                   OR created_at >= #{filter.from})
              AND (   #{filter.to} IS NULL
                   OR created_at <= #{filter.to})
            ORDER BY created_at DESC, order_id DESC
            """)
    List<OrderRow> listByAccount(OrderHistoryFilter filter);

    /**
     * The order row as read for cancellation and history. The columns are aliased to the
     * property names the result mapping uses.
     */
    class OrderRow {

        private String orderUuid;
        private Long clientId;
        private Long accountId;
        private String symbol;
        private OrderSide side;
        private Integer quantity;
        private BigDecimal price;
        private BigDecimal executedPrice;
        private OrderStatus status;
        private String idempotencyKey;
        private LocalDateTime createdAt;

        public OrderRow() {
        }

        public String getOrderUuid() {
            return orderUuid;
        }

        public void setOrderUuid(String orderUuid) {
            this.orderUuid = orderUuid;
        }

        public Long getClientId() {
            return clientId;
        }

        public void setClientId(Long clientId) {
            this.clientId = clientId;
        }

        public Long getAccountId() {
            return accountId;
        }

        public void setAccountId(Long accountId) {
            this.accountId = accountId;
        }

        public String getSymbol() {
            return symbol;
        }

        public void setSymbol(String symbol) {
            this.symbol = symbol;
        }

        public OrderSide getSide() {
            return side;
        }

        public void setSide(OrderSide side) {
            this.side = side;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public BigDecimal getPrice() {
            return price;
        }

        public void setPrice(BigDecimal price) {
            this.price = price;
        }

        public BigDecimal getExecutedPrice() {
            return executedPrice;
        }

        public void setExecutedPrice(BigDecimal executedPrice) {
            this.executedPrice = executedPrice;
        }

        public OrderStatus getStatus() {
            return status;
        }

        public void setStatus(OrderStatus status) {
            this.status = status;
        }

        public String getIdempotencyKey() {
            return idempotencyKey;
        }

        public void setIdempotencyKey(String idempotencyKey) {
            this.idempotencyKey = idempotencyKey;
        }

        public LocalDateTime getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(LocalDateTime createdAt) {
            this.createdAt = createdAt;
        }
    }

    /**
     * Parameter object for the insert. {@code orderType} is always {@code POSITION}; the status
     * and executed price are terminal in the synchronous Sprint 6 fill.
     */
    class OrderInsert {

        private Long clientId;
        private Long accountId;
        private String instrumentId;
        private String orderType;
        private OrderSide side;
        private Integer quantity;
        private BigDecimal price;
        private BigDecimal executedPrice;
        private String status;
        private String idempotencyKey;
        private String externalOrderId;
        private String orderUuid;

        public OrderInsert() {
        }

        public Long getClientId() {
            return clientId;
        }

        public void setClientId(Long clientId) {
            this.clientId = clientId;
        }

        public Long getAccountId() {
            return accountId;
        }

        public void setAccountId(Long accountId) {
            this.accountId = accountId;
        }

        public String getInstrumentId() {
            return instrumentId;
        }

        public void setInstrumentId(String instrumentId) {
            this.instrumentId = instrumentId;
        }

        public String getOrderType() {
            return orderType;
        }

        public void setOrderType(String orderType) {
            this.orderType = orderType;
        }

        public OrderSide getSide() {
            return side;
        }

        public void setSide(OrderSide side) {
            this.side = side;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public BigDecimal getPrice() {
            return price;
        }

        public void setPrice(BigDecimal price) {
            this.price = price;
        }

        public BigDecimal getExecutedPrice() {
            return executedPrice;
        }

        public void setExecutedPrice(BigDecimal executedPrice) {
            this.executedPrice = executedPrice;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getIdempotencyKey() {
            return idempotencyKey;
        }

        public void setIdempotencyKey(String idempotencyKey) {
            this.idempotencyKey = idempotencyKey;
        }

        public String getExternalOrderId() {
            return externalOrderId;
        }

        public void setExternalOrderId(String externalOrderId) {
            this.externalOrderId = externalOrderId;
        }

        public String getOrderUuid() {
            return orderUuid;
        }

        public void setOrderUuid(String orderUuid) {
            this.orderUuid = orderUuid;
        }
    }

    /**
     * The account-scoped history query. Nullable status, from and to filters; the SQL keeps the
     * statement parameterised by comparing each bind against {@code IS NULL}.
     */
    class OrderHistoryFilter {

        private Long clientId;
        private OrderStatus status;
        private LocalDateTime from;
        private LocalDateTime to;

        public OrderHistoryFilter() {
        }

        public Long getClientId() {
            return clientId;
        }

        public void setClientId(Long clientId) {
            this.clientId = clientId;
        }

        public OrderStatus getStatus() {
            return status;
        }

        public void setStatus(OrderStatus status) {
            this.status = status;
        }

        public LocalDateTime getFrom() {
            return from;
        }

        public void setFrom(LocalDateTime from) {
            this.from = from;
        }

        public LocalDateTime getTo() {
            return to;
        }

        public void setTo(LocalDateTime to) {
            this.to = to;
        }
    }
}