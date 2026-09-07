package com.team1.trading.api.service;

import com.team1.trading.domain.entity.Client;
import com.team1.trading.api.mapper.ClientMapper;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;

@Service
public class ClientService {

    private final ClientMapper clientMapper;

    public ClientService(ClientMapper clientMapper) {

        this.clientMapper = clientMapper;
    }

    public Optional<Client> getClientById(Long clientId) {

        return clientMapper.findById(clientId);
    }

    public List<Client> getAllClients() {

        return clientMapper.findAll();
    }

    public Optional<Client> getClientByAccountNumber(String accountNumber) {
        return clientMapper.findByAccountNumber(accountNumber);
    }

    public Client createClient(String accountNumber, String name, String email, String phone) {
        Client client = new Client(null, accountNumber, name, email, phone);
        clientMapper.save(client);
        return client;
    }

    public boolean updateClientProfile(Long clientId, String name, String email, String phone) {
        Client client = new Client(clientId, "", name, email, phone);
        return clientMapper.updateProfile(client) > 0;
    }

    public boolean activateClient(Long clientId) {
        return clientMapper.updateAccountState(clientId, "ACTIVE") > 0;
    }

    public boolean suspendClient(Long clientId) {
        return clientMapper.updateAccountState(clientId, "SUSPENDED") > 0;
    }

    public boolean closeClient(Long clientId) {
        return clientMapper.updateAccountState(clientId, "CLOSED") > 0;
    }
}
