package com.streamshield.api.stream;

import java.util.List;
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface StreamRepository extends JpaRepository<StreamEntity, UUID> {
    List<StreamEntity> findAllByTenantIdOrderByChannelNameAsc(UUID tenantId);
}
