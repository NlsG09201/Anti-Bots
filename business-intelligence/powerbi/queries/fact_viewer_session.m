let
    Source = PostgreSQL.Database(pServer, pDatabase),
    Warehouse = Source{[Schema = "bi", Item = "vw_powerbi_viewer_session"]}[Data],
    FillNullMeasures = Table.ReplaceValue(Warehouse, null, 0, Replacer.ReplaceValue, {
        "risk_score", "chat_messages", "watch_duration_seconds"
    }),
    SetTypes = Table.TransformColumnTypes(FillNullMeasures, {
        {"tenant_id", type text}, {"session_id", type text}, {"stream_id", type text},
        {"platform_key", type text}, {"channel_name", type text},
        {"joined_date", type date}, {"joined_at", type datetimezone},
        {"left_at", type datetimezone}, {"is_active", type logical},
        {"is_suspected_bot", type logical}, {"risk_score", type number},
        {"chat_messages", Int64.Type}, {"watch_duration_seconds", Int64.Type},
        {"source", type text}
    })
in
    SetTypes
