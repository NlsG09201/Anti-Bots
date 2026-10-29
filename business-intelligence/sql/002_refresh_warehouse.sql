-- Idempotent ETL. Run once per tenant after 001_warehouse.sql.
CREATE OR REPLACE PROCEDURE bi.refresh_warehouse(
    p_tenant_id uuid,
    p_from_date date DEFAULT current_date - 90
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_first_date date;
BEGIN
    SELECT LEAST(
        p_from_date,
        coalesce((SELECT min(v.joined_at::date)
                  FROM public.viewer_sessions v
                  JOIN public.streams s ON s.id = v.stream_id
                  WHERE s.tenant_id = p_tenant_id), p_from_date),
        coalesce((SELECT min(a.created_at::date)
                  FROM public.attacks a
                  JOIN public.streams s ON s.id = a.stream_id
                  WHERE s.tenant_id = p_tenant_id), p_from_date)
    ) INTO v_first_date;

    INSERT INTO bi.dim_date(date_key, full_date, year, quarter, month, month_name,
                            day_of_month, iso_week, day_of_week)
    SELECT to_char(d::date, 'YYYYMMDD')::integer, d::date,
           extract(year FROM d)::smallint, extract(quarter FROM d)::smallint,
           extract(month FROM d)::smallint, to_char(d, 'FMMonth'),
           extract(day FROM d)::smallint, extract(week FROM d)::smallint,
           extract(isodow FROM d)::smallint
    FROM generate_series(v_first_date, current_date, interval '1 day') AS d
    ON CONFLICT (full_date) DO NOTHING;

    INSERT INTO bi.dim_streamer(streamer_id, tenant_id, username, role, created_at)
    SELECT DISTINCT u.id, u.tenant_id, u.username, u.role::text, u.created_at
    FROM public.users u
    JOIN public.streams s ON s.owner_id = u.id
    WHERE s.tenant_id = p_tenant_id
    ON CONFLICT (streamer_id) DO UPDATE SET
        tenant_id = EXCLUDED.tenant_id,
        username = EXCLUDED.username,
        role = EXCLUDED.role;

    INSERT INTO bi.dim_stream(stream_id, tenant_id, streamer_id, platform_key,
                              channel_name, created_at, updated_at)
    SELECT s.id, s.tenant_id, s.owner_id, lower(s.platform::text), s.channel_name,
           s.created_at, s.updated_at
    FROM public.streams s
    WHERE s.tenant_id = p_tenant_id
    ON CONFLICT (stream_id) DO UPDATE SET
        tenant_id = EXCLUDED.tenant_id,
        streamer_id = EXCLUDED.streamer_id,
        platform_key = EXCLUDED.platform_key,
        channel_name = EXCLUDED.channel_name,
        updated_at = EXCLUDED.updated_at;

    INSERT INTO bi.fact_stream_snapshot(stream_id, snapshot_date, platform_key,
        is_live, viewer_count, active_chatters, suspicious_viewers, active_attacks,
        engagement_rate, threat_score, loaded_at)
    SELECT s.id, current_date, lower(s.platform::text), s.is_live,
        greatest(coalesce(s.viewer_count, 0), 0), v.active_chatters,
        v.suspicious_viewers, a.active_attacks,
        CASE WHEN coalesce(s.viewer_count, 0) > 0
             THEN v.active_chatters::numeric / s.viewer_count * 100 ELSE 0 END,
        greatest(coalesce(a.threat_score, 0), 0), now()
    FROM public.streams s
    LEFT JOIN LATERAL (
        SELECT count(*) FILTER (WHERE is_active)::integer AS active_chatters,
               count(*) FILTER (WHERE is_active AND is_suspected_bot)::integer AS suspicious_viewers
        FROM public.viewer_sessions
        WHERE stream_id = s.id
          AND lower(coalesce(behavior_metrics->>'source', '')) IN
              ('irc', 'helix', 'helix+irc', 'helix_chatters', 'kick_chat',
               'platform_kick', 'youtube_live_chat', 'platform_youtube',
               'tiktok_live_chat', 'platform_tiktok')
    ) v ON true
    LEFT JOIN LATERAL (
        SELECT count(*) FILTER (WHERE status = 'active')::integer AS active_attacks,
               coalesce(avg(risk_score), 0)::numeric AS threat_score
        FROM public.attacks WHERE stream_id = s.id
    ) a ON true
    WHERE s.tenant_id = p_tenant_id
    ON CONFLICT (stream_id, snapshot_date) DO UPDATE SET
        platform_key = EXCLUDED.platform_key,
        is_live = EXCLUDED.is_live,
        viewer_count = EXCLUDED.viewer_count,
        active_chatters = EXCLUDED.active_chatters,
        suspicious_viewers = EXCLUDED.suspicious_viewers,
        active_attacks = EXCLUDED.active_attacks,
        engagement_rate = EXCLUDED.engagement_rate,
        threat_score = EXCLUDED.threat_score,
        loaded_at = EXCLUDED.loaded_at;

    INSERT INTO bi.fact_viewer_session(session_id, stream_id, joined_date, joined_at,
        left_at, is_active, is_suspected_bot, risk_score, chat_messages,
        watch_duration_seconds, source, loaded_at)
    SELECT v.id, v.stream_id, v.joined_at::date, v.joined_at, v.left_at,
        v.is_active, v.is_suspected_bot, coalesce(v.risk_score, 0),
        coalesce(v.chat_messages, 0), coalesce(v.watch_duration_seconds, 0),
        coalesce(v.behavior_metrics->>'source', 'unknown'), now()
    FROM public.viewer_sessions v
    JOIN public.streams s ON s.id = v.stream_id
    WHERE s.tenant_id = p_tenant_id
    ON CONFLICT (session_id) DO UPDATE SET
        stream_id = EXCLUDED.stream_id,
        joined_date = EXCLUDED.joined_date,
        joined_at = EXCLUDED.joined_at,
        left_at = EXCLUDED.left_at,
        is_active = EXCLUDED.is_active,
        is_suspected_bot = EXCLUDED.is_suspected_bot,
        risk_score = EXCLUDED.risk_score,
        chat_messages = EXCLUDED.chat_messages,
        watch_duration_seconds = EXCLUDED.watch_duration_seconds,
        source = EXCLUDED.source,
        loaded_at = EXCLUDED.loaded_at;

    INSERT INTO bi.fact_attack(attack_id, stream_id, created_date, attack_type,
        severity, status, risk_score, confidence, affected_users,
        mitigation_action, created_at, mitigated_at, resolved_at, loaded_at)
    SELECT a.id, a.stream_id, a.created_at::date, lower(a.attack_type::text),
        lower(a.severity::text), a.status, coalesce(a.risk_score, 0),
        coalesce(a.confidence, 0), coalesce(a.affected_users, 0),
        lower(a.mitigation_action::text), a.created_at, a.mitigated_at,
        a.resolved_at, now()
    FROM public.attacks a
    JOIN public.streams s ON s.id = a.stream_id
    WHERE s.tenant_id = p_tenant_id
    ON CONFLICT (attack_id) DO UPDATE SET
        stream_id = EXCLUDED.stream_id,
        created_date = EXCLUDED.created_date,
        attack_type = EXCLUDED.attack_type,
        severity = EXCLUDED.severity,
        status = EXCLUDED.status,
        risk_score = EXCLUDED.risk_score,
        confidence = EXCLUDED.confidence,
        affected_users = EXCLUDED.affected_users,
        mitigation_action = EXCLUDED.mitigation_action,
        mitigated_at = EXCLUDED.mitigated_at,
        resolved_at = EXCLUDED.resolved_at,
        loaded_at = EXCLUDED.loaded_at;

    DELETE FROM bi.fact_chat_activity c
    USING bi.dim_stream s
    WHERE c.stream_id = s.stream_id
      AND s.tenant_id = p_tenant_id
      AND c.activity_date >= p_from_date;

    INSERT INTO bi.fact_chat_activity(stream_id, activity_date, event_type,
        messages, unique_users, suspicious_messages, average_risk_score, loaded_at)
    SELECT e.stream_id, e.created_at::date, lower(e.event_type), count(*),
        count(DISTINCT e.platform_user_id),
        count(*) FILTER (WHERE coalesce(e.risk_score, 0) >= 60),
        coalesce(avg(e.risk_score), 0), now()
    FROM public.stream_events e
    JOIN public.streams s ON s.id = e.stream_id
    WHERE s.tenant_id = p_tenant_id
      AND e.created_at >= p_from_date::timestamptz
      AND lower(e.event_type) IN ('chat_message', 'message', 'follow', 'user_follow', 'viewer_join', 'join')
    GROUP BY e.stream_id, e.created_at::date, lower(e.event_type);
END;
$$;
