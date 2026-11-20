let
    Source = GoogleBigQuery.Database([BillingProject = pBillingProjectId]),
    Project = Source{[Name = pProjectId]}[Data],
    Dataset = Project{[Name = pDataset, Kind = "Schema"]}[Data],
    Warehouse = Dataset{[Name = "dim_date", Kind = "Table"]}[Data],
    SetTypes = Table.TransformColumnTypes(Warehouse, {
        {"date_key", Int64.Type}, {"full_date", type date}, {"year", Int64.Type},
        {"quarter", Int64.Type}, {"month", Int64.Type}, {"month_name", type text},
        {"day_of_month", Int64.Type}, {"iso_week", Int64.Type},
        {"day_of_week", Int64.Type}
    })
in
    SetTypes
