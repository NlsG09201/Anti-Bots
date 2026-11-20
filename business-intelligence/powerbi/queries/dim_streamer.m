let
    Source = GoogleBigQuery.Database([BillingProject = pBillingProjectId]),
    Project = Source{[Name = pProjectId]}[Data],
    Dataset = Project{[Name = pDataset, Kind = "Schema"]}[Data],
    Warehouse = Dataset{[Name = "dim_streamer", Kind = "Table"]}[Data],
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
