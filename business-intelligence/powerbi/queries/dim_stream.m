let
    Source = GoogleBigQuery.Database([BillingProject = pBillingProjectId]),
    Project = Source{[Name = pProjectId]}[Data],
    Dataset = Project{[Name = pDataset, Kind = "Schema"]}[Data],
    Warehouse = Dataset{[Name = "dim_stream", Kind = "Table"]}[Data],
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
