using WetMap.Api.Domain;

namespace WetMap.Api.Application;

public interface IClock
{
    DateTimeOffset UtcNow { get; }
}

public interface IRadarManifestRepository
{
    Task<(RadarManifest Manifest, string ETag)> GetAsync(CancellationToken cancellationToken);
}

public interface IDmiForecastClient
{
    Task<IReadOnlyList<ForecastPoint>> GetAsync(double latitude, double longitude, CancellationToken cancellationToken);
}

public sealed class SystemClock : IClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;
}
