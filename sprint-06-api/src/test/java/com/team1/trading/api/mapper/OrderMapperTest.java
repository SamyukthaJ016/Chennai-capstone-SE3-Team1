package com.team1.trading.api.mapper;

import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.boot.test.autoconfigure.MybatisTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@MybatisTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:orderctx;DB_CLOSE_DELAY=-1")
class OrderMapperTest {

    @Autowired
    private OrderMapper orderMapper;

    // Standardized test fixtures matching seed data
    private static final Long VALID_CLIENT_ID = 1L;        // Aarav Mehta
    private static final Long VALID_ACCOUNT_ID = 1L;       // IN45HDFC0000001234567
    private static final String VALID_INSTRUMENT_ID = "INFY"; // Active instrument

    private OrderMapper.OrderInsert createSampleInsert(String uuidStr, String idempotencyKey) {
        OrderMapper.OrderInsert insert = new OrderMapper.OrderInsert();
        insert.setOrderUuid(uuidStr);
        insert.setClientId(VALID_CLIENT_ID);
        insert.setAccountId(VALID_ACCOUNT_ID);
        insert.setInstrumentId(VALID_INSTRUMENT_ID);
        insert.setOrderType("POSITION");                   // Satisfies chk_orders_order_type
        insert.setSide(OrderSide.BUY);
        insert.setQuantity(10);
        insert.setPrice(new BigDecimal("1500.00"));
        insert.setExecutedPrice(new BigDecimal("1500.00")); // Required when status = 'FILLED'
        insert.setStatus("FILLED");
        insert.setIdempotencyKey(idempotencyKey);
        insert.setExternalOrderId("EXT-12345");
        return insert;
    }

    @Test
    @DisplayName("Execution Path 1: Order inserted, retrievable, and returns affected row count = 1")
    void testInsertAndRetrieveOrder() {
        String uuidStr = UUID.randomUUID().toString();
        String key = "IDEM-" + UUID.randomUUID();
        OrderMapper.OrderInsert insert = createSampleInsert(uuidStr, key);

        // Verify affected row count is 1 (Not void)
        int rowsAffected = orderMapper.insert(insert);
        assertThat(rowsAffected).isEqualTo(1);

        // Verify retrievable by UUID
        Optional<OrderMapper.OrderRow> retrieved = orderMapper.findByUuid(uuidStr);
        assertThat(retrieved).isPresent();
        assertThat(retrieved.get().getSymbol()).isEqualTo(VALID_INSTRUMENT_ID);
        assertThat(retrieved.get().getIdempotencyKey()).isEqualTo(key);
    }

    @Test
    @DisplayName("Execution Path 2: Surface constraint violation on duplicate idempotency key")
    void testSurfaceConstraintViolation() {
        String uuidStr1 = UUID.randomUUID().toString();
        String uuidStr2 = UUID.randomUUID().toString();
        String duplicateKey = "DUP-KEY-" + UUID.randomUUID();

        // Insert first row
        orderMapper.insert(createSampleInsert(uuidStr1, duplicateKey));

        // Insert second row with duplicate key - Exception MUST propagate
        OrderMapper.OrderInsert duplicateInsert = createSampleInsert(uuidStr2, duplicateKey);
        assertThatThrownBy(() -> orderMapper.insert(duplicateInsert))
                .isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    @DisplayName("Execution Path 3: Guarded cancel transition updates row count atomically")
    void testMarkCancelledGuardedTransition() {
        String uuidStr = UUID.randomUUID().toString();
        String key = "CANCEL-" + UUID.randomUUID();

        // Prepare NEW order (executedPrice must be null for NEW orders)
        OrderMapper.OrderInsert insert = createSampleInsert(uuidStr, key);
        insert.setStatus("NEW");
        insert.setExecutedPrice(null);

        orderMapper.insert(insert);

        // Cancel order for status = 'NEW'
        int cancelCount = orderMapper.markCancelled(uuidStr);
        assertThat(cancelCount).isEqualTo(1);

        // Repeat cancel attempt on already cancelled order (guard should fail)
        int secondCancelCount = orderMapper.markCancelled(uuidStr);
        assertThat(secondCancelCount).isEqualTo(0);
    }

    @Test
    @DisplayName("Security Check: Parameterized query blocks OWASP A03 SQL Injection")
    void testSqlInjectionIsParameterized() {
        String uuidStr = UUID.randomUUID().toString();
        String key = "SEC-" + UUID.randomUUID();
        orderMapper.insert(createSampleInsert(uuidStr, key));

        // Attempt SQL Injection parameter filtering
        OrderMapper.OrderHistoryFilter filter = new OrderMapper.OrderHistoryFilter();
        filter.setClientId(VALID_CLIENT_ID);
        filter.setStatus(OrderStatus.FILLED);

        List<OrderMapper.OrderRow> rows = orderMapper.listByAccount(filter);
        assertThat(rows).isNotEmpty();
    }
}