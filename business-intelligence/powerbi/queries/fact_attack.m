let
    Source = PostgreSQL.Database(pServer, pDatabase),
    Warehouse = Source{[Schema = "bi", Item = "vw_powerbi_attack"]}[Data],
    NormalizeLabels = Table.TransformColumns(Warehouse, {
        {"attack_type", each Text.Lower(Text.Trim(Text.From(_))), type text},
        {"severity", each Text.Lower(Text.Trim(Text.From(_))), type text},
        {"status", each Text.Lower(Text.Trim(Text.From(_))), type text},
        {"mitigation_action", each Text.Lower(Text.Trim(Text.From(_))), type text}
    }),
    SetTypes = Table.TransformColumnTypes(NormalizeLabels, {
        {"tenant_id", type text}, {"attack_id", type text}, {"stream_id", type text},
        {"platform_key", type text}, {"channel_name", type text},
        {"created_date", type date}, {"attack_type", type text}, {"severity", type text},
        {"status", type text}, {"risk_score", type number}, {"confidence", type number},
        {"affected_users", Int64.Type}, {"mitigation_action", type text},
        {"created_at", type datetimezone}, {"mitigated_at", type datetimezone},
        {"resolved_at", type datetimezone}
    })
in
    SetTypes
