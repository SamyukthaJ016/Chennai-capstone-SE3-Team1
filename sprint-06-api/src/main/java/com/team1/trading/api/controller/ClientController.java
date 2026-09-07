package com.team1.trading.api.controller;

import com.team1.trading.domain.entity.Client;
import com.team1.trading.api.dto.CreateClientRequest;
import com.team1.trading.api.dto.ClientResponse;
import com.team1.trading.api.service.ClientService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/clients")
public class ClientController {

    private final ClientService clientService;

    public ClientController(ClientService clientService) {
        this.clientService = clientService;
    }

    @PostMapping
    public ResponseEntity<ClientResponse> addClient(@Valid @RequestBody CreateClientRequest request) {
        Client client = clientService.createClient(
                request.getAccountNumber(),
                request.getName(),
                request.getEmail(),
                request.getPhone()
        );
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(mapToResponse(client));
    }

    @GetMapping("/{clientId}")
    public ResponseEntity<ClientResponse> getClient(@PathVariable Long clientId) {
        return clientService.getClientById(clientId)
                .map(client -> ResponseEntity.ok(mapToResponse(client)))
                .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping
    public List<ClientResponse> getAllClients() {
        return clientService.getAllClients().stream()
                .map(this::mapToResponse)
                .toList();
    }

    @GetMapping("/account/{accountNumber}")
    public ResponseEntity<ClientResponse> getClientByAccountNumber(@PathVariable String accountNumber) {
        return clientService.getClientByAccountNumber(accountNumber)
                .map(client -> ResponseEntity.ok(mapToResponse(client)))
                .orElse(ResponseEntity.notFound().build());
    }

    @PutMapping("/{clientId}/profile")
    public ResponseEntity<Void> updateProfile(@PathVariable Long clientId,
                                               @Valid @RequestBody CreateClientRequest request) {
        boolean updated = clientService.updateClientProfile(
                clientId,
                request.getName(),
                request.getEmail(),
                request.getPhone()
        );
        return updated ? ResponseEntity.ok().build() : ResponseEntity.notFound().build();
    }

    @PutMapping("/{clientId}/activate")
    public ResponseEntity<Void> activateClient(@PathVariable Long clientId) {
        boolean updated = clientService.activateClient(clientId);
        return updated ? ResponseEntity.ok().build() : ResponseEntity.notFound().build();
    }

    @PutMapping("/{clientId}/suspend")
    public ResponseEntity<Void> suspendClient(@PathVariable Long clientId) {
        boolean updated = clientService.suspendClient(clientId);
        return updated ? ResponseEntity.ok().build() : ResponseEntity.notFound().build();
    }

    @PutMapping("/{clientId}/close")
    public ResponseEntity<Void> closeClient(@PathVariable Long clientId) {
        boolean updated = clientService.closeClient(clientId);
        return updated ? ResponseEntity.ok().build() : ResponseEntity.notFound().build();
    }

    private ClientResponse mapToResponse(Client client) {
        return new ClientResponse(
                client.getClientId(),
                client.getAccountNumber(),
                client.getName(),
                client.getEmail(),
                client.getPhone(),
                client.getCreatedOn(),
                client.getAccountState(),
                client.getWalletBalance()
        );
    }
}
