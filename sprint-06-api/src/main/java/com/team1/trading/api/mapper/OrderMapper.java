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
 * Parameterised MyBatis Mapper for the orders table (OWASP A03 Compliant).
 */
@Mapper
public interface OrderMapper {

    @Insert("""
            INSERT INTO orders (
                order_id, client_id, account_id, instrument_id, order_type, side, 
                quantity, price, executed_price, status, idempotency_key, 
                external_order_id, created_at, updated_at
            ) VALUES (
                #{order.orderUuid}::uuid, #{order.clientId}, #{order.accountId}, 
                #{order.instrumentId}, #{order.orderType}, #{order.side}, 
                #{order.quantity}, #{order.price}, #{order.executedPrice}, 
                #{order.status}, #{order.idempotencyKey}, #{order.externalOrderId}, 
                now(), now()
            )
            """)
    int insert(@Param("order") OrderInsert order);

    @Select("""
            SELECT order_id AS orderUuid, client_id AS clientId, account_id AS accountId,
                   instrument_id AS symbol, side, quantity, price, executed_price AS executedPrice,
                   status, idempotency_key AS idempotencyKey, created_at AS createdAt
            FROM orders
            WHERE order_id = #{orderUuid}::uuid
            """)
    Optional<OrderRow> findByUuid(@Param("orderUuid") String orderUuid);

    @Update("""
            UPDATE orders
            SET status     = 'CANCELLED',
                updated_at = now()
            WHERE order_id = #{orderUuid}::uuid
              AND status   = 'NEW'
            """)
    int markCancelled(@Param("orderUuid") String orderUuid);

    @Select("""
            SELECT order_id AS orderUuid, client_id AS clientId, account_id AS accountId,
                   instrument_id AS symbol, side, quantity, price, executed_price AS executedPrice,
                   status, idempotency_key AS idempotencyKey, created_at AS createdAt
            FROM orders
            WHERE client_id = #{filter.clientId}
              AND (#{filter.status, jdbcType=VARCHAR}::varchar IS NULL OR status = #{filter.status, jdbcType=VARCHAR}::varchar)
              AND (#{filter.from, jdbcType=TIMESTAMP}::timestamp IS NULL OR created_at >= #{filter.from, jdbcType=TIMESTAMP}::timestamp)
              AND (#{filter.to, jdbcType=TIMESTAMP}::timestamp IS NULL OR created_at <= #{filter.to, jdbcType=TIMESTAMP}::timestamp)
            ORDER BY created_at DESC
            """)
    List<OrderRow> listByAccount(@Param("filter") OrderHistoryFilter filter);

    // --- DTOs / Records for Clean Data Transfer ---

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

        public String getOrderUuid() { return orderUuid; }
        public void setOrderUuid(String orderUuid) { this.orderUuid = orderUuid; }
        public Long getClientId() { return clientId; }
        public void setClientId(Long clientId) { this.clientId = clientId; }
        public Long getAccountId() { return accountId; }
        public void setAccountId(Long accountId) { this.accountId = accountId; }
        public String getSymbol() { return symbol; }
        public void setSymbol(String symbol) { this.symbol = symbol; }
        public OrderSide getSide() { return side; }
        public void setSide(OrderSide side) { this.side = side; }
        public Integer getQuantity() { return quantity; }
        public void setQuantity(Integer quantity) { this.quantity = quantity; }
        public BigDecimal getPrice() { return price; }
        public void setPrice(BigDecimal price) { this.price = price; }
        public BigDecimal getExecutedPrice() { return executedPrice; }
        public void setExecutedPrice(BigDecimal executedPrice) { this.executedPrice = executedPrice; }
        public OrderStatus getStatus() { return status; }
        public void setStatus(OrderStatus status) { this.status = status; }
        public String getIdempotencyKey() { return idempotencyKey; }
        public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
        public LocalDateTime getCreatedAt() { return createdAt; }
        public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    }

    class OrderInsert {
        private String orderUuid;
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

        public String getOrderUuid() { return orderUuid; }
        public void setOrderUuid(String orderUuid) { this.orderUuid = orderUuid; }
        public Long getClientId() { return clientId; }
        public void setClientId(Long clientId) { this.clientId = clientId; }
        public Long getAccountId() { return accountId; }
        public void setAccountId(Long accountId) { this.accountId = accountId; }
        public String getInstrumentId() { return instrumentId; }
        public void setInstrumentId(String instrumentId) { this.instrumentId = instrumentId; }
        public String getOrderType() { return orderType; }
        public void setOrderType(String orderType) { this.orderType = orderType; }
        public OrderSide getSide() { return side; }
        public void setSide(OrderSide side) { this.side = side; }
        public Integer getQuantity() { return quantity; }
        public void setQuantity(Integer quantity) { this.quantity = quantity; }
        public BigDecimal getPrice() { return price; }
        public void setPrice(BigDecimal price) { this.price = price; }
        public BigDecimal getExecutedPrice() { return executedPrice; }
        public void setExecutedPrice(BigDecimal executedPrice) { this.executedPrice = executedPrice; }
        public String getStatus() { return status; }
        public void setStatus(String status) { this.status = status; }
        public String getIdempotencyKey() { return idempotencyKey; }
        public void setIdempotencyKey(String idempotencyKey) { this.idempotencyKey = idempotencyKey; }
        public String getExternalOrderId() { return externalOrderId; }
        public void setExternalOrderId(String externalOrderId) { this.externalOrderId = externalOrderId; }
    }

    class OrderHistoryFilter {
        private Long clientId;
        private OrderStatus status;
        private LocalDateTime from;
        private LocalDateTime to;

        public Long getClientId() { return clientId; }
        public void setClientId(Long clientId) { this.clientId = clientId; }
        public OrderStatus getStatus() { return status; }
        public void setStatus(OrderStatus status) { this.status = status; }
        public LocalDateTime getFrom() { return from; }
        public void setFrom(LocalDateTime from) { this.from = from; }
        public LocalDateTime getTo() { return to; }
        public void setTo(LocalDateTime to) { this.to = to; }
    }
}