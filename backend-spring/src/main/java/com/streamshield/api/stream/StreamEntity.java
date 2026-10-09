package com.streamshield.api.stream;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "streams")
public class StreamEntity {
    @Id
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Column(name = "platform", nullable = false)
    private String platform;

    @Column(name = "channel_name", nullable = false)
    private String channelName;

    @Column(name = "is_live", nullable = false)
    private boolean live;

    @Column(name = "viewer_count", nullable = false)
    private int viewerCount;

    protected StreamEntity() {}

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public String getPlatform() { return platform; }
    public String getChannelName() { return channelName; }
    public boolean isLive() { return live; }
    public int getViewerCount() { return viewerCount; }
}
