package com.team1.trading.api.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.Optional;

/**
 * SQL for the instruments table. The instrument symbol is the primary key, so the contract's
 * {@code symbol} binds straight onto {@code instrument_id}.
 */
@Mapper
public interface InstrumentMapper {

    @Select("""
            SELECT instrument_id, instrument_name, active, updated_on
            FROM instruments
            WHERE instrument_id = #{symbol}
            """)
    Optional<InstrumentRow> findRowBySymbol(@Param("symbol") String symbol);

    /**
     * The instrument row as read for an order. {@link com.team1.trading.domain.entity.Instrument}
     * decides tradability from these columns; the API layer never reimplements that rule.
     */
    class InstrumentRow {

        private String instrumentId;
        private String instrumentName;
        private boolean active;
        private LocalDateTime updatedOn;

        public InstrumentRow() {
        }

        public String getInstrumentId() {
            return instrumentId;
        }

        public void setInstrumentId(String instrumentId) {
            this.instrumentId = instrumentId;
        }

        public String getInstrumentName() {
            return instrumentName;
        }

        public void setInstrumentName(String instrumentName) {
            this.instrumentName = instrumentName;
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        public LocalDateTime getUpdatedOn() {
            return updatedOn;
        }

        public void setUpdatedOn(LocalDateTime updatedOn) {
            this.updatedOn = updatedOn;
        }
    }
}