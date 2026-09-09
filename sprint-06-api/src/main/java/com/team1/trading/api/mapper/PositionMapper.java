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
 * Parameterised MyBatis Mapper for portfolio_positions and portfolio_holding tables (OWASP A03 Compliant).
 */
@Mapper
public interface PositionMapper {

    @Select("""
            SELECT client_id AS accountId, instrument_id AS symbol, quantity, price_per_unit AS pricePerUnit
            FROM portfolio_positions
            WHERE client_id = #{accountId}
              AND instrument_id = #{symbol}
            """)
    Optional<PositionRow> findHeld(@Param("accountId") Long accountId, @Param("symbol") String symbol);

    @Select("""
            SELECT client_id AS accountId, instrument_id AS symbol, quantity, price_per_unit AS averageCost
            FROM portfolio_positions
            WHERE client_id = #{accountId}
              AND quantity > 0
            ORDER BY instrument_id ASC
            """)
    List<PositionResponse> listPositions(@Param("accountId") Long accountId);

    @Insert("""
            INSERT INTO portfolio_positions (client_id, instrument_id, quantity, price_per_unit, updated_at)
            VALUES (#{pos.accountId}, #{pos.symbol}, #{pos.quantity}, #{pos.price}, now())
            ON CONFLICT (client_id, instrument_id)
            DO UPDATE SET quantity = portfolio_positions.quantity + EXCLUDED.quantity,
                          price_per_unit = EXCLUDED.price_per_unit,
                          updated_at = now()
            """)
    int upsertBuy(@Param("pos") PositionWrite pos);

    @Insert("""
            INSERT INTO portfolio_holding (client_id, instrument_id, quantity, price_per_unit, updated_at)
            VALUES (#{pos.accountId}, #{pos.symbol}, #{pos.quantity}, #{pos.price}, now())
            ON CONFLICT (client_id, instrument_id)
            DO UPDATE SET quantity = portfolio_holding.quantity + EXCLUDED.quantity,
                          price_per_unit = EXCLUDED.price_per_unit,
                          updated_at = now()
            """)
    int upsertBuyHolding(@Param("pos") PositionWrite pos);

    @Update("""
            UPDATE portfolio_positions
            SET quantity = quantity - #{pos.quantity},
                updated_at = now()
            WHERE client_id = #{pos.accountId}
              AND instrument_id = #{pos.symbol}
              AND quantity >= #{pos.quantity}
            """)
    int reduceSell(@Param("pos") PositionWrite pos);

    @Update("""
            UPDATE portfolio_holding
            SET quantity = quantity - #{pos.quantity},
                updated_at = now()
            WHERE client_id = #{pos.accountId}
              AND instrument_id = #{pos.symbol}
              AND quantity >= #{pos.quantity}
            """)
    int reduceSellHolding(@Param("pos") PositionWrite pos);

    // --- Inner DTOs ---

    class PositionRow {
        private Long accountId;
        private String symbol;
        private Integer quantity;
        private BigDecimal pricePerUnit;

        public Long getAccountId() { return accountId; }
        public void setAccountId(Long accountId) { this.accountId = accountId; }

        public String getSymbol() { return symbol; }
        public void setSymbol(String symbol) { this.symbol = symbol; }

        public Integer getQuantity() { return quantity; }
        public void setQuantity(Integer quantity) { this.quantity = quantity; }

        public BigDecimal getPricePerUnit() { return pricePerUnit; }
        public void setPricePerUnit(BigDecimal pricePerUnit) { this.pricePerUnit = pricePerUnit; }
    }

    class PositionWrite {
        private Long accountId;
        private String symbol;
        private Integer quantity;
        private BigDecimal price;

        public PositionWrite() {}

        public PositionWrite(Long accountId, String symbol, Integer quantity, BigDecimal price) {
            this.accountId = accountId;
            this.symbol = symbol;
            this.quantity = quantity;
            this.price = price;
        }

        public Long getAccountId() { return accountId; }
        public void setAccountId(Long accountId) { this.accountId = accountId; }

        public String getSymbol() { return symbol; }
        public void setSymbol(String symbol) { this.symbol = symbol; }

        public Integer getQuantity() { return quantity; }
        public void setQuantity(Integer quantity) { this.quantity = quantity; }

        public BigDecimal getPrice() { return price; }
        public void setPrice(BigDecimal price) { this.price = price; }
    }
}