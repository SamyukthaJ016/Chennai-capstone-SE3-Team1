package com.team1.trading.api.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.Optional;

@Mapper
public interface InstrumentMapper {

    @Select("""
            SELECT instrument_id AS instrumentId, instrument_name AS instrumentName,
                   active, updated_on AS updatedOn
            FROM instruments
            WHERE instrument_id = #{symbol}
            """)
    Optional<InstrumentRow> findRowBySymbol(@Param("symbol") String symbol);

    class InstrumentRow {
        private String instrumentId;
        private String instrumentName;
        private boolean active;
        private LocalDateTime updatedOn;

        public String getInstrumentId() { return instrumentId; }
        public void setInstrumentId(String instrumentId) { this.instrumentId = instrumentId; }

        public String getInstrumentName() { return instrumentName; }
        public void setInstrumentName(String instrumentName) { this.instrumentName = instrumentName; }

        public boolean isActive() { return active; }
        public void setActive(boolean active) { this.active = active; }

        public LocalDateTime getUpdatedOn() { return updatedOn; }
        public void setUpdatedOn(LocalDateTime updatedOn) { this.updatedOn = updatedOn; }
    }
}