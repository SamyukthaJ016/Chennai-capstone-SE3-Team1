package com.team1.trading.api.controller;

import com.team1.trading.domain.entity.BankAccount;
import com.team1.trading.api.dto.CreateBankAccountRequest;
import com.team1.trading.api.service.BankAccountService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.math.BigDecimal;
import java.util.List;

@RestController
@RequestMapping("/api/bank-accounts")
public class BankAccountController {

    private final BankAccountService bankAccountService;

    public BankAccountController(BankAccountService bankAccountService) {
        this.bankAccountService = bankAccountService;
    }

    @PostMapping
    public ResponseEntity<BankAccount> createBankAccount(@Valid @RequestBody CreateBankAccountRequest request) {
        BankAccount bankAccount = bankAccountService.createBankAccount(
                request.getClientId(),
                request.getAccountNumber(),
                request.getName(),
                request.getPhone(),
                request.getEmail(),
                request.getBankName(),
                request.getIfscCode(),
                request.getInitialBalance()
        );
        return ResponseEntity.status(HttpStatus.CREATED).body(bankAccount);
    }

    @GetMapping("/account/{accountNumber}")
    public ResponseEntity<BankAccount> getBankAccountByAccountNumber(@PathVariable String accountNumber) {
        return bankAccountService.getBankAccountByAccountNumber(accountNumber)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/client/{clientId}")
    public ResponseEntity<BankAccount> getBankAccountByClientId(@PathVariable Long clientId) {
        return bankAccountService.getBankAccountByClientId(clientId)
                .map(ResponseEntity::ok)
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping
    public List<BankAccount> getAllBankAccounts() {
        return bankAccountService.getAllBankAccounts();
    }

    @PutMapping("/{accountNumber}/contact")
    public ResponseEntity<Void> updateContact(@PathVariable String accountNumber,
                                              @RequestParam String phone,
                                              @RequestParam String email) {
        boolean updated = bankAccountService.updateContact(accountNumber, phone, email);
        return updated ? ResponseEntity.ok().build() : ResponseEntity.notFound().build();
    }

    @PutMapping("/{accountNumber}/deposit")
    public ResponseEntity<Void> deposit(@PathVariable String accountNumber,
                                        @RequestParam BigDecimal amount) {
        boolean updated = bankAccountService.deposit(accountNumber, amount);
        return updated ? ResponseEntity.ok().build() : ResponseEntity.notFound().build();
    }

    @PutMapping("/{accountNumber}/withdraw")
    public ResponseEntity<Void> withdraw(@PathVariable String accountNumber,
                                         @RequestParam BigDecimal amount) {
        boolean updated = bankAccountService.withdraw(accountNumber, amount);
        return updated ? ResponseEntity.ok().build() : ResponseEntity.notFound().build();
    }
}
