package com.team1.trading.api.service;

import com.team1.trading.api.dto.AccountResponse;
import com.team1.trading.api.dto.BalanceResponse;
import com.team1.trading.api.dto.OrderHistoryEntry;
import com.team1.trading.api.dto.PositionResponse;
import com.team1.trading.api.mapper.AccountMapper;
import com.team1.trading.api.mapper.AccountMapper.AccountRow;
import com.team1.trading.api.mapper.OrderMapper;
import com.team1.trading.api.mapper.OrderMapper.OrderHistoryFilter;
import com.team1.trading.api.mapper.OrderMapper.OrderRow;
import com.team1.trading.api.mapper.PositionMapper;
import com.team1.trading.domain.entity.types.OrderSide;
import com.team1.trading.domain.entity.types.OrderStatus;
import com.team1.trading.domain.exception.AccountNotActiveException;
import com.team1.trading.domain.exception.AccountNotFoundException;
import com.team1.trading.domain.exception.InvalidOrderException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

/**
 * Unit tests of the account read endpoints against mocked mappers. Every read proves existence,
 * token reachability and activeness before answering, all through the domain's own
 * {@code canTrade()} decision.
 */
@ExtendWith(MockitoExtension.class)
class AccountServiceTest {

    private static final Long ACCOUNT_ID = 1L;

    @Mock
    private AccountMapper accountMapper;
    @Mock
    private OrderMapper orderMapper;
    @Mock
    private PositionMapper positionMapper;

    private AccountService accountService;

    @BeforeEach
    void setUp() {
        accountService = new AccountService(accountMapper, orderMapper, positionMapper, "USD");
    }

    private AccountRow activeAccount() {
        AccountRow row = new AccountRow();
        row.setClientId(ACCOUNT_ID);
        row.setAccountNumber("ACC-000001");
        row.setName("Priya Menon");
        row.setEmail("priya@example.com");
        row.setPhone("+91 90000 00000");
        row.setCreatedOn(LocalDateTime.of(2026, 1, 1, 8, 0));
        row.setAccountState("ACTIVE");
        row.setWalletBalance(new BigDecimal("24500.75"));
        row.setVersion(7);
        row.setUpdatedOn(LocalDateTime.of(2026, 9, 28, 9, 14, 22));
        return row;
    }

    @Nested
    @DisplayName("The shared existence, reach and activeness gate")
    class GateTests {

        @Test
        @DisplayName("A missing account is ACC-404")
        void missingAccount() {
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.empty());

            assertThatThrownBy(() -> accountService.getAccount(ACCOUNT_ID, null))
                    .isInstanceOf(AccountNotFoundException.class)
                    .hasMessage("Account not found");
        }

        @Test
        @DisplayName("A token that cannot reach the account is ACC-403")
        void tokenCannotReach() {
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.of(activeAccount()));

            assertThatThrownBy(() -> accountService.getBalance(ACCOUNT_ID, 5L))
                    .isInstanceOf(AccountNotActiveException.class)
                    .hasMessage("Account not active");
        }

        @Test
        @DisplayName("An inactive account is ACC-403")
        void inactiveAccount() {
            AccountRow row = activeAccount();
            row.setAccountState("CLOSED");
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.of(row));

            assertThatThrownBy(() -> accountService.getPositions(ACCOUNT_ID, null))
                    .isInstanceOf(AccountNotActiveException.class)
                    .hasMessage("Account not active");
            verify(positionMapper, org.mockito.Mockito.never()).listPositions(any());
        }
    }

    @Nested
    @DisplayName("Account details and cash balance")
    class AccountAndBalanceTests {

        @Test
        @DisplayName("Account details map every row field, including version and last updated")
        void getAccount_mapsRow() {
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.of(activeAccount()));

            AccountResponse response = accountService.getAccount(ACCOUNT_ID, null);

            assertThat(response.getId()).isEqualTo(ACCOUNT_ID);
            assertThat(response.getAccountId()).isEqualTo("ACC-000001");
            assertThat(response.getHolderName()).isEqualTo("Priya Menon");
            assertThat(response.getCashBalance()).isEqualByComparingTo(new BigDecimal("24500.75"));
            assertThat(response.getStatus()).isEqualTo("ACTIVE");
            assertThat(response.getVersion()).isEqualTo(7);
            assertThat(response.getLastUpdated()).isEqualTo(LocalDateTime.of(2026, 9, 28, 9, 14, 22));
        }

        @Test
        @DisplayName("The balance carries the configured ISO 4217 currency")
        void getBalance_usesConfiguredCurrency() {
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.of(activeAccount()));

            BalanceResponse response = accountService.getBalance(ACCOUNT_ID, null);

            assertThat(response.getAccountId()).isEqualTo(ACCOUNT_ID);
            assertThat(response.getCashBalance()).isEqualByComparingTo(new BigDecimal("24500.75"));
            assertThat(response.getCurrency()).isEqualTo("USD");
            assertThat(response.getAsOf()).isNotNull();
        }
    }

    @Nested
    @DisplayName("Positions and order history")
    class ReadsTests {

        @Test
        @DisplayName("Positions come back as the contract's entries")
        void getPositions() {
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.of(activeAccount()));
            given(positionMapper.listPositions(ACCOUNT_ID))
                    .willReturn(List.of(new PositionResponse(ACCOUNT_ID, "ACME", 100, new BigDecimal("25.50"))));

            List<PositionResponse> positions = accountService.getPositions(ACCOUNT_ID, null);

            assertThat(positions).singleElement().satisfies(position -> {
                assertThat(position.getSymbol()).isEqualTo("ACME");
                assertThat(position.getQuantity()).isEqualTo(100);
                assertThat(position.getAverageCost()).isEqualByComparingTo(new BigDecimal("25.50"));
            });
        }

        @Test
        @DisplayName("a valid status filter reaches the mapper and rows become contract entries")
        void getOrderHistory_passesFilter() {
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.of(activeAccount()));
            OrderRow row = new OrderRow();
            row.setOrderUuid("6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e");
            row.setClientId(ACCOUNT_ID);
            row.setAccountId(ACCOUNT_ID);
            row.setSymbol("ACME");
            row.setSide(OrderSide.BUY);
            row.setQuantity(100);
            row.setPrice(new BigDecimal("25.50"));
            row.setExecutedPrice(new BigDecimal("25.50"));
            row.setStatus(OrderStatus.FILLED);
            row.setIdempotencyKey("6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e");
            row.setCreatedAt(LocalDateTime.of(2026, 9, 28, 9, 14, 22));
            given(orderMapper.listByAccount(any())).willReturn(List.of(row));

            List<OrderHistoryEntry> entries = accountService.getOrderHistory(
                    ACCOUNT_ID, null, "FILLED", null, null);

            ArgumentCaptor<OrderHistoryFilter> filterCaptor = ArgumentCaptor.forClass(OrderHistoryFilter.class);
            verify(orderMapper).listByAccount(filterCaptor.capture());
            assertThat(filterCaptor.getValue().getClientId()).isEqualTo(ACCOUNT_ID);
            assertThat(filterCaptor.getValue().getStatus()).isEqualTo(OrderStatus.FILLED);

            assertThat(entries).singleElement().satisfies(entry -> {
                assertThat(entry.getOrderId()).isEqualTo("ORD-6f2b1c2a-6a1e-4a4f-9c0d-2f7a1b3c4d5e");
                assertThat(entry.getStatus()).isEqualTo(OrderStatus.FILLED);
                assertThat(entry.getExecutedPrice()).isEqualByComparingTo(new BigDecimal("25.50"));
                assertThat(entry.getCreatedOn()).isEqualTo(LocalDateTime.of(2026, 9, 28, 9, 14, 22));
            });
        }

        @Test
        @DisplayName("An unknown status value is VAL-422 and never reaches the mapper")
        void getOrderHistory_unknownStatus() {
            given(accountMapper.findRow(ACCOUNT_ID)).willReturn(Optional.of(activeAccount()));

            assertThatThrownBy(() -> accountService.getOrderHistory(ACCOUNT_ID, null, "BOGUS", null, null))
                    .isInstanceOf(InvalidOrderException.class)
                    .hasMessage("Invalid input");
            verify(orderMapper, org.mockito.Mockito.never()).listByAccount(any());
        }
    }
}