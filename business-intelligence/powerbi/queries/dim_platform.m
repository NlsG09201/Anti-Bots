let
    Source = GoogleBigQuery.Database([BillingProject = pBillingProjectId]),
    Project = Source{[Name = pProjectId]}[Data],
    Dataset = Project{[Name = pDataset, Kind = "Schema"]}[Data],
    Warehouse = Dataset{[Name = "dim_platform", Kind = "Table"]}[Data],
    SetTypes = Table.TransformColumnTypes(Warehouse, {
        {"platform_key", type text}, {"platform_name", type text}
    })
in
    SetTypes
