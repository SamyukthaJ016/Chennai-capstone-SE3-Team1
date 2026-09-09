package com.team1.trading.api.mapper;

import com.team1.trading.api.dto.PositionResponse;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

/**
 * SQL for the two portfolio tables. Every statement is fully parameterised with {@code #{} binds
 * and nothing else.
 *
 * <p>The buy is a single upsert: on conflict it recalculates the weighted average cost in the
 * database, which is the behaviour the domain's own cost model defines. The sell is guarded with
 * {@code quantity >= #{quantity}}, so it can never take a position negative.
 */
@Mapper
public interface PositionMapper {

    @Select("""
            SELECT client_id      AS accountId,
                   instrument_id  AS symbol,
                   quantity,
                   price_per_unit AS averageCost
            FROM portfolio_positions
            WHERE client_id = #{clientId}
              AND quantity > 0
            ORDER BY instrument_id
            """)
    List<PositionResponse> listPositions(@Param("clientId") Long clientId);

    @Select("""
            SELECT quantity, price_per_unit AS pricePerUnit
            FROM portfolio_positions
            WHERE client_id = #{clientId}
              AND instrument_id = #{symbol}
            """)
    Optional<PositionRow> findHeld(@Param("clientId") Long clientId, @Param("symbol") String symbol);

    @Insert("""
            INSERT INTO portfolio_positions (client_id, instrument_id, quantity, price_per_unit,
                                             created_at, updated_at)
            VALUES (#{update.clientId}, #{update.symbol}, #{update.quantity},
                    #{update.pricePerUnit}, now(), now())
            ON CONFLICT (client_id, instrument_id)
            DO UPDATE SET
                quantity = portfolio_positions.quantity + EXCLUDED.quantity,
                price_per_unit = (portfolio_positions.quantity * portfolio_positions.price_per_unit
                                + EXCLUDED.quantity * EXCLUDED.price_per_unit)
                               / (portfolio_positions.quantity + EXCLUDED.quantity),
                updated_at = now()
            """)
    int upsertBuy(PositionWrite update);

    @Update("""
            UPDATE portfolio_positions
            SET quantity    = quantity - #{update.quantity},
                updated_at  = now()
            WHERE client_id = #{update.clientId}
              AND instrument_id = #{update.symbol}
              AND quantity  >= #{update.quantity}
            """)
    int reduceSell(PositionWrite update);

    @Insert("""
            INSERT INTO portfolio_holding (client_id, instrument_id, quantity, price_per_unit,
                                           created_at, updated_at)
            VALUES (#{update.clientId}, #{update.symbol}, #{update.quantity},
                    #{update.pricePerUnit}, now(), now())
            ON CONFLICT (client_id, instrument_id)
            DO UPDATE SET
                quantity = portfolio_holding.quantity + EXCLUDED.quantity,
                price_per_unit = (portfolio_holding.quantity * portfolio_holding.price_per_unit
                                + EXCLUDED.quantity * EXCLUDED.price_per_unit)
                               / (portfolio_holding.quantity + EXCLUDED.quantity),
                updated_at = now()
            """)
    int upsertBuyHolding(PositionWrite update);

    @Update("""
            UPDATE portfolio_holding
            SET quantity    = quantity - #{update.quantity},
                updated_at  = now()
            WHERE client_id = #{update.clientId}
              AND instrument_id = #{update.symbol}
              AND quantity  >= #{update.quantity}
            """)
    int reduceSellHolding(PositionWrite update);

    /**
     * The held quantity read for a sell order.
     */
    class PositionRow {

        private Integer quantity;
        private BigDecimal pricePerUnit;

        public PositionRow() {
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public BigDecimal getPricePerUnit() {
            return pricePerUnit;
        }

        public void setPricePerUnit(BigDecimal pricePerUnit) {
            this.pricePerUnit = pricePerUnit;
        }
    }

    /**
     * Parameter object for both portfolio write statements.
     */
    class PositionWrite {

        private Long clientId;
        private String symbol;
        private Integer quantity;
        private BigDecimal pricePerUnit;

        public PositionWrite() {
        }

        public PositionWrite(Long clientId, String symbol, Integer quantity, BigDecimal pricePerUnit) {
            this.clientId = clientId;
            this.symbol = symbol;
            this.quantity = quantity;
            this.pricePerUnit = pricePerUnit;
        }

        public Long getClientId() {
            return clientId;
        }

        public void setClientId(Long clientId) {
            this.clientId = clientId;
        }

        public String getSymbol() {
            return symbol;
        }

        public void setSymbol(String symbol) {
            this.symbol = symbol;
        }

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }

        public BigDecimal getPricePerUnit() {
            return pricePerUnit;
        }

        public void setPricePerUnit(BigDecimal pricePerUnit) {
            this.pricePerUnit = pricePerUnit;
        }
    }
}