let
    Source = PostgreSQL.Database(pServer, pDatabase),
    Warehouse = Source{[Schema = "bi", Item = "vw_powerbi_dim_stream"]}[Data],
    CleanText = Table.TransformColumns(Warehouse, {
        {"channel_name", each Text.Trim(Text.Clean(Text.From(_))), type text}
    }),
    SetTypes = Table.TransformColumnTypes(CleanText, {
        {"stream_key", Int64.Type}, {"stream_id", type text}, {"tenant_id", type text},
        {"streamer_id", type text}, {"platform_key", type text},
        {"created_at", type datetimezone}, {"updated_at", type datetimezone}
    })
in
    SetTypes
