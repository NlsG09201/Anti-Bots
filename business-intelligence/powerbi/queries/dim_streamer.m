let
    Source = PostgreSQL.Database(pServer, pDatabase),
    Warehouse = Source{[Schema = "bi", Item = "vw_powerbi_dim_streamer"]}[Data],
    CleanText = Table.TransformColumns(Warehouse, {
        {"username", each Text.Trim(Text.Clean(Text.From(_))), type text},
        {"role", each Text.Lower(Text.Trim(Text.From(_))), type text}
    }),
    SetTypes = Table.TransformColumnTypes(CleanText, {
        {"streamer_key", Int64.Type}, {"streamer_id", type text},
        {"tenant_id", type text}, {"created_at", type datetimezone}
    })
in
    SetTypes
