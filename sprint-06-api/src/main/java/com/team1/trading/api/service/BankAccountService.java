package com.team1.trading.api.service;

import com.team1.trading.domain.entity.BankAccount;
import com.team1.trading.api.mapper.BankAccountMapper;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

@Service
public class BankAccountService {

    private final BankAccountMapper bankAccountMapper;

    public BankAccountService(BankAccountMapper bankAccountMapper) {
        this.bankAccountMapper = bankAccountMapper;
    }

    public Optional<BankAccount> getBankAccountByAccountNumber(String accountNumber) {
        return bankAccountMapper.findByAccountNumber(accountNumber);
    }

    public Optional<BankAccount> getBankAccountByClientId(Long clientId) {
        return bankAccountMapper.findByClientId(clientId);
    }

    public List<BankAccount> getAllBankAccounts() {
        return bankAccountMapper.findAll();
    }

    public BankAccount createBankAccount(Long clientId, String accountNumber, String name, String phone,
                                        String email, String bankName, String ifscCode, BigDecimal initialBalance) {
        BankAccount bankAccount = new BankAccount(clientId, accountNumber, name, phone, email, bankName, ifscCode);
        if (initialBalance != null && initialBalance.compareTo(BigDecimal.ZERO) > 0) {
            bankAccount.deposit(initialBalance);
        }
        bankAccountMapper.save(bankAccount);
        return bankAccount;
    }

    public boolean updateContact(String accountNumber, String phone, String email) {
        BankAccount bankAccount = new BankAccount(null, accountNumber, null, phone, email, null, null);
        return bankAccountMapper.updateContact(bankAccount) > 0;
    }

    public boolean deposit(String accountNumber, BigDecimal amount) {
        Optional<BankAccount> accountOpt = bankAccountMapper.findByAccountNumber(accountNumber);
        if (accountOpt.isPresent()) {
            BankAccount account = accountOpt.get();
            account.deposit(amount);
            return bankAccountMapper.updateBalance(accountNumber, account.getBalance()) > 0;
        }
        return false;
    }

    public boolean withdraw(String accountNumber, BigDecimal amount) {
        Optional<BankAccount> accountOpt = bankAccountMapper.findByAccountNumber(accountNumber);
        if (accountOpt.isPresent()) {
            BankAccount account = accountOpt.get();
            account.withdraw(amount);
            return bankAccountMapper.updateBalance(accountNumber, account.getBalance()) > 0;
        }
        return false;
    }
}
