let
    Source = PostgreSQL.Database(pServer, pDatabase),
    Warehouse = Source{[Schema = "bi", Item = "dim_platform"]}[Data],
    SetTypes = Table.TransformColumnTypes(Warehouse, {
        {"platform_key", type text}, {"platform_name", type text}
    })
in
    SetTypes
