// Create Power Query parameters pServer (Text) and pDatabase (Text) in Power BI.
// Set credentials in Power BI's data-source settings; do not embed passwords here.
let
    Source = PostgreSQL.Database(pServer, pDatabase),
    Warehouse = Source{[Schema = "bi", Item = "vw_powerbi_stream_snapshot"]}[Data],
    KeepColumns = Table.SelectColumns(Warehouse, {
        "snapshot_date", "tenant_id", "stream_id", "streamer_id", "platform_key",
        "platform_name", "channel_name", "is_live", "viewer_count",
        "active_chatters", "suspicious_viewers", "active_attacks",
        "engagement_rate", "threat_score", "loaded_at"
    }),
    CleanChannelText = Table.TransformColumns(KeepColumns, {
        {"channel_name", each Text.Trim(Text.Clean(Text.From(_))), type text},
        {"platform_name", each Text.Proper(Text.Trim(Text.Clean(Text.From(_)))), type text}
    }),
    FillNullCounts = Table.ReplaceValue(CleanChannelText, null, 0, Replacer.ReplaceValue, {
        "viewer_count", "active_chatters", "suspicious_viewers", "active_attacks",
        "engagement_rate", "threat_score"
    }),
    SetTypes = Table.TransformColumnTypes(FillNullCounts, {
        {"snapshot_date", type date}, {"tenant_id", type text}, {"stream_id", type text},
        {"streamer_id", type text}, {"platform_key", type text}, {"platform_name", type text},
        {"channel_name", type text}, {"is_live", type logical}, {"viewer_count", Int64.Type},
        {"active_chatters", Int64.Type}, {"suspicious_viewers", Int64.Type},
        {"active_attacks", Int64.Type}, {"engagement_rate", type number},
        {"threat_score", type number}, {"loaded_at", type datetimezone}
    }),
    ValidRows = Table.SelectRows(SetTypes, each [stream_id] <> null and [snapshot_date] <> null),
    OneSnapshotPerStreamDay = Table.Distinct(ValidRows, {"stream_id", "snapshot_date"}),
    MergePlatformDimension = Table.NestedJoin(OneSnapshotPerStreamDay, {"platform_key"},
        Source{[Schema = "bi", Item = "dim_platform"]}[Data], {"platform_key"},
        "PlatformDimension", JoinKind.LeftOuter),
    ExpandPlatform = Table.ExpandTableColumn(MergePlatformDimension, "PlatformDimension",
        {"platform_name"}, {"platform_name_dimension"}),
    PreferDimensionName = Table.AddColumn(ExpandPlatform, "platform_display", each
        if [platform_name_dimension] = null then [platform_name] else [platform_name_dimension], type text),
    AddEngagementPercent = Table.AddColumn(PreferDimensionName, "chat_coverage_percent", each
        if [viewer_count] = 0 then 0 else Number.Round([active_chatters] / [viewer_count] * 100, 2), type number),
    AddRiskBand = Table.AddColumn(AddEngagementPercent, "risk_band", each
        if [threat_score] >= 80 then "Critical"
        else if [threat_score] >= 60 then "High"
        else if [threat_score] >= 35 then "Elevated"
        else "Stable", type text),
    AddMonthStart = Table.AddColumn(AddRiskBand, "month_start", each Date.StartOfMonth([snapshot_date]), type date),
    RemoveHelperColumns = Table.RemoveColumns(AddMonthStart, {"platform_name_dimension"})
in
    RemoveHelperColumns
