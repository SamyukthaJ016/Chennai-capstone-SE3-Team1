package com.team1.trading.domain.entity;

import java.time.LocalDateTime;
import java.util.Objects;
import java.util.UUID;

public class Auth {

    private UUID clientId;
    private String email;
    private String passwordHash;
    private LocalDateTime created;
    private LocalDateTime updated;

    public Auth(UUID clientId, String email, String passwordHash) {
        this.clientId = clientId;
        this.email = email;
        this.passwordHash = passwordHash;
        this.created = LocalDateTime.now();
        this.updated = this.created;
    }

    public Auth(UUID clientId, String email, String passwordHash, LocalDateTime created, LocalDateTime updated) {
        this.clientId = clientId;
        this.email = email;
        this.passwordHash = passwordHash;
        this.created = created;
        this.updated = updated;
    }

    public UUID getClientId() {
        return clientId;
    }

    public String getEmail() {
        return email;
    }

    public LocalDateTime getCreated() {
        return created;
    }

    public LocalDateTime getUpdated() {
        return updated;
    }

    /**
     * Compares against the stored hash. The actual hashing (bcrypt or
     * similar) happens outside this class, at whatever layer receives the
     * raw password - Auth only ever holds and compares hashes.
     */
    public boolean authenticate(String candidateHash) {
        return this.passwordHash.equals(candidateHash);
    }

    public void changePassword(String newPasswordHash) {
        this.passwordHash = newPasswordHash;
        this.updated = LocalDateTime.now();
    }

    // resetPassword() left out deliberately - whether it means "generate
    // and email a temporary credential" or "invalidate and force a reset
    // flow" is a security decision, not something to guess at.

}