package com.team1.trading.api.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Optional;

/**
 * SQL for the account (clients) table. Every statement is fully parameterised with
 * {@code #{} binds and nothing else.
 *
 * <p>The cash update is the optimistic-lock guard required by contracts/trade-api.yaml: it
 * succeeds only when the client-supplied version still matches the row, and it advances the
 * version in the same statement. A concurrent write therefore takes the version away from the
 * caller and the update reports zero rows.
 */
@Mapper
public interface AccountMapper {

    @Select("""
            SELECT client_id, account_number, name, email, phone, created_on, account_state,
                   wallet_balance, version, updated_on
            FROM clients
            WHERE client_id = #{clientId}
            """)
    Optional<AccountRow> findRow(@Param("clientId") Long clientId);

    @Update("""
            UPDATE clients
            SET wallet_balance = #{update.newBalance},
                version        = version + 1,
                updated_on     = now()
            WHERE client_id = #{update.clientId}
              AND version   = #{update.expectedVersion}
            """)
    int updateCashGuarded(AccountCashUpdate update);

    /**
     * The account row as the API reads it. Carries the optimistic-lock version and the
     * {@code updated_on} stamp that {@code AccountResponse} reports.
     */
    class AccountRow {

        private Long clientId;
        private String accountNumber;
        private String name;
        private String email;
        private String phone;
        private LocalDateTime createdOn;
        private String accountState;
        private BigDecimal walletBalance;
        private Integer version;
        private LocalDateTime updatedOn;

        public AccountRow() {
        }

        public Long getClientId() {
            return clientId;
        }

        public void setClientId(Long clientId) {
            this.clientId = clientId;
        }

        public String getAccountNumber() {
            return accountNumber;
        }

        public void setAccountNumber(String accountNumber) {
            this.accountNumber = accountNumber;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }

        public String getPhone() {
            return phone;
        }

        public void setPhone(String phone) {
            this.phone = phone;
        }

        public LocalDateTime getCreatedOn() {
            return createdOn;
        }

        public void setCreatedOn(LocalDateTime createdOn) {
            this.createdOn = createdOn;
        }

        public String getAccountState() {
            return accountState;
        }

        public void setAccountState(String accountState) {
            this.accountState = accountState;
        }

        public BigDecimal getWalletBalance() {
            return walletBalance;
        }

        public void setWalletBalance(BigDecimal walletBalance) {
            this.walletBalance = walletBalance;
        }

        public Integer getVersion() {
            return version;
        }

        public void setVersion(Integer version) {
            this.version = version;
        }

        public LocalDateTime getUpdatedOn() {
            return updatedOn;
        }

        public void setUpdatedOn(LocalDateTime updatedOn) {
            this.updatedOn = updatedOn;
        }
    }

    /**
     * The guarded cash write: the expected version the caller read, so a concurrent write
     * makes the statement match zero rows.
     */
    class AccountCashUpdate {

        private Long clientId;
        private BigDecimal newBalance;
        private Integer expectedVersion;

        public AccountCashUpdate() {
        }

        public AccountCashUpdate(Long clientId, BigDecimal newBalance, Integer expectedVersion) {
            this.clientId = clientId;
            this.newBalance = newBalance;
            this.expectedVersion = expectedVersion;
        }

        public Long getClientId() {
            return clientId;
        }

        public void setClientId(Long clientId) {
            this.clientId = clientId;
        }

        public BigDecimal getNewBalance() {
            return newBalance;
        }

        public void setNewBalance(BigDecimal newBalance) {
            this.newBalance = newBalance;
        }

        public Integer getExpectedVersion() {
            return expectedVersion;
        }

        public void setExpectedVersion(Integer expectedVersion) {
            this.expectedVersion = expectedVersion;
        }
    }
}