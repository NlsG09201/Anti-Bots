package com.streamshield.api.user;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "users")
public class UserEntity {
    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "is_active", nullable = false)
    private boolean active;

    protected UserEntity() {}

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public boolean isActive() { return active; }
}
