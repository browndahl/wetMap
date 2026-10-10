namespace WetMap.Api.Domain;

public static class DmiCredit
{
    public const string Attribution = "Baseret på data fra DMI og efterfølgende bearbejdet";
}

public sealed record RadarFrame(
    string Id,
    DateTimeOffset ObservedAt,
    DateTimeOffset FetchedAt,
    string Url,
    double[] Bounds,
    string Product,
    string Unit,
    string Sha256);

public sealed record RadarManifest(
    int SchemaVersion,
    DateTimeOffset GeneratedAt,
    string Attribution,
    IReadOnlyList<RadarFrame> Frames);

public sealed record ForecastPoint(
    DateTimeOffset Step,
    double? TemperatureC,
    double? PrecipitationKgM2,
    double? WindSpeedMs,
    double? CloudCoverPercent);

public sealed record ForecastResponse(
    double Latitude,
    double Longitude,
    DateTimeOffset FetchedAt,
    string Attribution,
    IReadOnlyList<ForecastPoint> Points);
