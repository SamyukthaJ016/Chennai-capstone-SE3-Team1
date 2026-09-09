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

@Mapper
public interface PositionMapper {

    @Select("""
            SELECT account_id AS accountId, instrument_id AS symbol, quantity, avg_price AS pricePerUnit
            FROM positions
            WHERE account_id = #{accountId}
              AND instrument_id = #{symbol}
            """)
    Optional<PositionRow> findHeld(@Param("accountId") Long accountId, @Param("symbol") String symbol);

    @Select("""
            SELECT instrument_id AS symbol, quantity, avg_price AS pricePerUnit
            FROM positions
            WHERE account_id = #{accountId}
            """)
    List<PositionResponse> listPositions(@Param("accountId") Long accountId);

    @Insert("""
            INSERT INTO positions (account_id, instrument_id, quantity, avg_price)
            VALUES (#{pos.accountId}, #{pos.symbol}, #{pos.quantity}, #{pos.price})
            ON CONFLICT (account_id, instrument_id)
            DO UPDATE SET quantity = positions.quantity + EXCLUDED.quantity,
                          avg_price = EXCLUDED.avg_price
            """)
    int upsertBuy(@Param("pos") PositionWrite pos);

    @Insert("""
            INSERT INTO holdings (account_id, instrument_id, quantity)
            VALUES (#{pos.accountId}, #{pos.symbol}, #{pos.quantity})
            ON CONFLICT (account_id, instrument_id)
            DO UPDATE SET quantity = holdings.quantity + EXCLUDED.quantity
            """)
    int upsertBuyHolding(@Param("pos") PositionWrite pos);

    @Update("""
            UPDATE positions
            SET quantity = quantity - #{pos.quantity}
            WHERE account_id = #{pos.accountId}
              AND instrument_id = #{pos.symbol}
              AND quantity >= #{pos.quantity}
            """)
    int reduceSell(@Param("pos") PositionWrite pos);

    @Update("""
            UPDATE holdings
            SET quantity = quantity - #{pos.quantity}
            WHERE account_id = #{pos.accountId}
              AND instrument_id = #{pos.symbol}
              AND quantity >= #{pos.quantity}
            """)
    int reduceSellHolding(@Param("pos") PositionWrite pos);

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