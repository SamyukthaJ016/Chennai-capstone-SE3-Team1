package com.team1.trading.domain.entity;

import java.time.LocalDateTime;
import java.util.Objects;

public class Auth {
    private String email;
    private String passwordHash;
    private LocalDateTime created;
    private LocalDateTime updated;
    private Integer version;

    public Auth(Long clientId, String email, String passwordHash) {

        this.email = email;
        this.passwordHash =passwordHash;
        this.created = LocalDateTime.now();
        this.updated = this.created;
        this.version = 0;
    }

    public Auth( String email, String passwordHash, LocalDateTime created, LocalDateTime updated, Integer version) {
        this.email = email;
        this.passwordHash = passwordHash;
        this.created = Objects.requireNonNull(created, "created must not be null");
        this.updated = Objects.requireNonNull(updated, "updated must not be null");
        this.version = Objects.requireNonNull(version, "version must not be null");
    }


    public String getEmail() { return email; }
    public LocalDateTime getCreated() { return created; }
    public LocalDateTime getUpdated() { return updated; }
    public Integer getVersion() { return version; }


    public boolean authenticate(String candidateHash) {
        return this.passwordHash.equals(candidateHash);
    }


    public void changePassword(String newPasswordHash) {
        this.passwordHash = newPasswordHash;
        this.updated = LocalDateTime.now();
        this.version++;
    }

}