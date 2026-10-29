let
    Source = PostgreSQL.Database(pServer, pDatabase),
    Warehouse = Source{[Schema = "bi", Item = "vw_powerbi_chat_activity"]}[Data],
    NormalizeEventType = Table.TransformColumns(Warehouse, {
        {"event_type", each Text.Lower(Text.Trim(Text.From(_))), type text}
    }),
    FillNullMeasures = Table.ReplaceValue(NormalizeEventType, null, 0, Replacer.ReplaceValue, {
        "messages", "unique_users", "suspicious_messages", "average_risk_score"
    }),
    SetTypes = Table.TransformColumnTypes(FillNullMeasures, {
        {"tenant_id", type text}, {"stream_id", type text}, {"platform_key", type text},
        {"channel_name", type text}, {"activity_date", type date},
        {"event_type", type text}, {"messages", Int64.Type},
        {"unique_users", Int64.Type}, {"suspicious_messages", Int64.Type},
        {"average_risk_score", type number}
    })
in
    SetTypes
