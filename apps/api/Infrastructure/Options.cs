namespace WetMap.Api.Infrastructure;

public sealed class DmiOptions
{
    public const string Section = "Dmi";
    public string BaseUrl { get; init; } = "https://opendataapi.dmi.dk";
    public int TimeoutSeconds { get; init; } = 20;
    public int ForecastCacheMinutes { get; init; } = 10;
}

public sealed class StorageOptions
{
    public const string Section = "Storage";
    public string FramesDirectory { get; init; } = "/data/frames";
}
