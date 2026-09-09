package com.team1.trading.api.mapper;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mybatis.spring.boot.test.autoconfigure.MybatisTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import java.math.BigDecimal;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

@MybatisTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.datasource.url=jdbc:h2:mem:accountctx;DB_CLOSE_DELAY=-1")
class AccountMapperTest {

    @Autowired
    private AccountMapper accountMapper;

    // Matches Aarav Mehta from clients seed data
    private static final Long SEED_ACCOUNT_ID = 1L;

    @Test
    @DisplayName("Execution Path 1: Account read correctly by account ID")
    void testFindRow() {
        Optional<AccountMapper.AccountRow> accountOpt = accountMapper.findRow(SEED_ACCOUNT_ID);

        assertThat(accountOpt).isPresent();
        AccountMapper.AccountRow row = accountOpt.get();
        assertThat(row.getClientId()).isEqualTo(SEED_ACCOUNT_ID);
        assertThat(row.getName()).isEqualTo("Aarav Mehta");
        assertThat(row.getAccountState()).isEqualTo("ACTIVE");
        assertThat(row.getWalletBalance()).isNotNull();
        assertThat(row.getVersion()).isNotNull();
    }

    @Test
    @DisplayName("Execution Path 2: Guarded cash update succeeds with matching version and returns 1 affected row")
    void testUpdateCashGuardedSuccess() {
        // Fetch initial state
        AccountMapper.AccountRow initial = accountMapper.findRow(SEED_ACCOUNT_ID).orElseThrow();
        BigDecimal newBalance = initial.getWalletBalance().add(new BigDecimal("500.00"));

        // Execute guarded cash update using current Integer version
        AccountMapper.AccountCashUpdate update = new AccountMapper.AccountCashUpdate(
                SEED_ACCOUNT_ID, newBalance, initial.getVersion());

        int rowsAffected = accountMapper.updateCashGuarded(update);

        // Assert 1 row affected and wallet balance updated
        assertThat(rowsAffected).isEqualTo(1);

        AccountMapper.AccountRow updated = accountMapper.findRow(SEED_ACCOUNT_ID).orElseThrow();
        assertThat(updated.getWalletBalance()).isEqualByComparingTo(newBalance);
        assertThat(updated.getVersion()).isEqualTo(initial.getVersion() + 1);
    }

    @Test
    @DisplayName("Execution Path 3: Guarded cash update fails (0 rows affected) if version changed concurrently")
    void testUpdateCashGuardedVersionMismatch() {
        AccountMapper.AccountRow initial = accountMapper.findRow(SEED_ACCOUNT_ID).orElseThrow();
        Integer staleVersion = initial.getVersion() - 1; // Simulate stale Integer version

        AccountMapper.AccountCashUpdate update = new AccountMapper.AccountCashUpdate(
                SEED_ACCOUNT_ID, new BigDecimal("999999.00"), staleVersion);

        int rowsAffected = accountMapper.updateCashGuarded(update);

        // Assert 0 rows affected due to optimistic concurrency guard
        assertThat(rowsAffected).isEqualTo(0);
    }
}