package com.team1.trading.domain.entity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Client is the account: it holds the wallet balance and the account state.
 */
class AccountTest {

    private Client account;

    @BeforeEach
    void setUp() {
        account = new Client(1L, 1001, "Ada Lovelace", "ada@example.com", "9000000001");
    }

    @Nested
    @DisplayName("Account state")
    class StateTests {

        @Test
        @DisplayName("A new account starts ACTIVE")
        void newAccount_startsActive() {
            assertEquals("ACTIVE", account.getAccountState());
        }

        @Test
        @DisplayName("suspend() moves the account to SUSPENDED")
        void suspend_movesToSuspended() {
            account.suspend();

            assertEquals("SUSPENDED", account.getAccountState());
        }

        @Test
        @DisplayName("deactivate() moves the account to INACTIVE")
        void deactivate_movesToInactive() {
            account.deactivate();

            assertEquals("INACTIVE", account.getAccountState());
        }

        @Test
        @DisplayName("activate() lifts a suspension, so the suspension is reversible")
        void activate_liftsSuspension() {
            account.suspend();

            account.activate();

            assertEquals("ACTIVE", account.getAccountState());
        }

        @Test
        @DisplayName("An ACTIVE account may trade")
        void canTrade_trueWhenActive() {
            assertTrue(account.canTrade());
        }

        @Test
        @DisplayName("A SUSPENDED account may not trade")
        void canTrade_falseWhenSuspended() {
            account.suspend();

            assertFalse(account.canTrade());
        }

        @Test
        @DisplayName("An INACTIVE account may not trade")
        void canTrade_falseWhenInactive() {
            account.deactivate();

            assertFalse(account.canTrade());
        }
    }

    @Nested
    @DisplayName("Credit")
    class CreditTests {

        @Test
        @DisplayName("credit() increases the balance by the amount")
        void credit_increasesBalance() {
            account.credit(new BigDecimal("100.00"));

            assertEquals(0, new BigDecimal("100.00").compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("Two credits accumulate")
        void credit_twice_accumulates() {
            account.credit(new BigDecimal("100.00"));
            account.credit(new BigDecimal("25.50"));

            assertEquals(0, new BigDecimal("125.50").compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("credit() of zero leaves the balance unchanged")
        void credit_zero_leavesBalanceUnchanged() {
            account.credit(new BigDecimal("50.00"));

            account.credit(BigDecimal.ZERO);

            assertEquals(0, new BigDecimal("50.00").compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("credit() of a negative amount is refused")
        void credit_negativeAmount_isRefused() {
            assertThrows(IllegalArgumentException.class,
                    () -> account.credit(new BigDecimal("-0.01")));
        }

        @Test
        @DisplayName("credit() of null is refused")
        void credit_null_isRefused() {
            assertThrows(IllegalArgumentException.class, () -> account.credit(null));
        }
    }

    @Nested
    @DisplayName("Debit")
    class DebitTests {

        @BeforeEach
        void fund() {
            account.credit(new BigDecimal("100.00"));
        }

        @Test
        @DisplayName("debit() decreases the balance by the amount")
        void debit_decreasesBalance() {
            account.debit(new BigDecimal("30.00"));

            assertEquals(0, new BigDecimal("70.00").compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("debit() of the exact balance leaves zero")
        void debit_exactBalance_leavesZero() {
            account.debit(new BigDecimal("100.00"));

            assertEquals(0, BigDecimal.ZERO.compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("debit() of one penny more than the balance is refused")
        void debit_onePennyOverBalance_isRefused() {
            assertThrows(IllegalStateException.class,
                    () -> account.debit(new BigDecimal("100.01")));
        }

        @Test
        @DisplayName("A refused debit leaves the balance untouched, so nothing is subtracted first")
        void debit_refused_leavesBalanceUntouched() {
            assertThrows(IllegalStateException.class,
                    () -> account.debit(new BigDecimal("100.01")));

            assertEquals(0, new BigDecimal("100.00").compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("The balance never goes negative")
        void debit_neverLeavesBalanceNegative() {
            assertThrows(IllegalStateException.class,
                    () -> account.debit(new BigDecimal("1000.00")));

            assertTrue(account.getWalletBalance().signum() >= 0);
        }

        @Test
        @DisplayName("debit() of zero leaves the balance unchanged")
        void debit_zero_leavesBalanceUnchanged() {
            account.debit(BigDecimal.ZERO);

            assertEquals(0, new BigDecimal("100.00").compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("debit() of a negative amount is refused")
        void debit_negativeAmount_isRefused() {
            assertThrows(IllegalArgumentException.class,
                    () -> account.debit(new BigDecimal("-0.01")));
        }

        @Test
        @DisplayName("debit() of null is refused")
        void debit_null_isRefused() {
            assertThrows(IllegalArgumentException.class, () -> account.debit(null));
        }
    }

    @Nested
    @DisplayName("Affordability")
    class AffordabilityTests {

        @BeforeEach
        void fund() {
            account.credit(new BigDecimal("100.00"));
        }

        @Test
        @DisplayName("An amount below the balance is affordable")
        void canAfford_trueBelowBalance() {
            assertTrue(account.canAfford(new BigDecimal("99.99")));
        }

        @Test
        @DisplayName("An amount exactly equal to the balance is affordable")
        void canAfford_trueAtExactBalance() {
            assertTrue(account.canAfford(new BigDecimal("100.00")));
        }

        @Test
        @DisplayName("One penny above the balance is not affordable")
        void canAfford_falseOnePennyAbove() {
            assertFalse(account.canAfford(new BigDecimal("100.01")));
        }

        @Test
        @DisplayName("Nothing is affordable on an empty account except zero")
        void canAfford_falseOnEmptyAccount() {
            Client empty = new Client(2L, 1002, "Grace Hopper", "grace@example.com", "9000000002");

            assertFalse(empty.canAfford(new BigDecimal("0.01")));
        }

        @Test
        @DisplayName("Asking whether an amount is affordable does not move the balance")
        void canAfford_doesNotChangeBalance() {
            account.canAfford(new BigDecimal("100.00"));

            assertEquals(0, new BigDecimal("100.00").compareTo(account.getWalletBalance()));
        }
    }

    @Nested
    @DisplayName("Money precision")
    class MoneyPrecisionTests {

        @Test
        @DisplayName("A new wallet is zero at two decimal places")
        void newWallet_isZeroAtTwoDecimalPlaces() {
            assertEquals(new BigDecimal("0.00"), account.getWalletBalance());
        }

        @Test
        @DisplayName("A thousand credits of 0.10 come to exactly 100.00, with no drift")
        void money_doesNotDriftOverAThousandCredits() {
            for (int i = 0; i < 1000; i++) {
                account.credit(new BigDecimal("0.10"));
            }

            assertEquals(0, new BigDecimal("100.00").compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("A thousand credits and debits of 0.10 come back to exactly zero")
        void money_doesNotDriftOverMixedOperations() {
            for (int i = 0; i < 1000; i++) {
                account.credit(new BigDecimal("0.10"));
                account.debit(new BigDecimal("0.10"));
            }

            assertEquals(0, BigDecimal.ZERO.compareTo(account.getWalletBalance()));
        }

        @Test
        @DisplayName("A third of a penny is never introduced by a credit")
        void money_keepsTwoDecimalPlacesAfterCredit() {
            account.credit(new BigDecimal("10.005"));

            assertTrue(account.getWalletBalance().scale() <= 2,
                    "balance kept more than two decimal places: " + account.getWalletBalance());
        }
    }

    @Nested
    @DisplayName("Identity and profile")
    class IdentityTests {

        @Test
        @DisplayName("A new account generates its own clientId")
        void newAccount_generatesClientId() {
            assertNotNull(account.getClientId());
        }

        @Test
        @DisplayName("Two new accounts do not share a clientId")
        void newAccounts_haveDistinctClientIds() {
            Client other = new Client(2L, 1002, "Grace Hopper", "grace@example.com", "9000000002");

            assertNotEquals(account.getClientId(), other.getClientId());
        }

        @Test
        @DisplayName("The numeric userId and the UUID clientId are separate identifiers")
        void userId_andClientId_areSeparateIdentifiers() {
            assertEquals(1L, account.getUserId());
            assertNotNull(account.getClientId());
        }

        @Test
        @DisplayName("An account rebuilt from storage keeps the values it was given")
        void reconstructedAccount_keepsItsValues() {
            UUID clientId = UUID.randomUUID();
            LocalDateTime createdOn = LocalDateTime.now().minusDays(3);

            Client stored = new Client(clientId, 7L, 1007, "Alan Turing", "alan@example.com",
                    "9000000007", createdOn, "SUSPENDED", new BigDecimal("42.50"));

            assertEquals(clientId, stored.getClientId());
            assertEquals("SUSPENDED", stored.getAccountState());
            assertEquals(0, new BigDecimal("42.50").compareTo(stored.getWalletBalance()));
        }

        @Test
        @DisplayName("An account cannot be built without an account number")
        void newAccount_withoutAccountNumber_isRefused() {
            assertThrows(NullPointerException.class,
                    () -> new Client(3L, null, "No Number", "none@example.com", "9000000003"));
        }

        @Test
        @DisplayName("updateProfile() changes the contact details and nothing else")
        void updateProfile_changesContactDetailsOnly() {
            account.credit(new BigDecimal("10.00"));

            account.updateProfile("Ada King", "ada.king@example.com", "9000000009");

            assertEquals("Ada King", account.getName());
            assertEquals("ada.king@example.com", account.getEmail());
            assertEquals("9000000009", account.getPhone());
            assertEquals(0, new BigDecimal("10.00").compareTo(account.getWalletBalance()));
        }
    }
}
