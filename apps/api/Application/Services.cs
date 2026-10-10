using Microsoft.Extensions.Caching.Memory;
using WetMap.Api.Domain;

namespace WetMap.Api.Application;

public sealed class RadarService(IRadarManifestRepository repository)
{
    public Task<(RadarManifest Manifest, string ETag)> GetAsync(CancellationToken cancellationToken) =>
        repository.GetAsync(cancellationToken);
}

public sealed class ForecastService(IDmiForecastClient client, IMemoryCache cache, IClock clock)
{
    public async Task<ForecastResponse> GetAsync(double latitude, double longitude, CancellationToken cancellationToken)
    {
        var roundedLatitude = Math.Round(latitude, 3);
        var roundedLongitude = Math.Round(longitude, 3);
        var cacheKey = $"forecast:{roundedLatitude:F3}:{roundedLongitude:F3}";
        var points = await cache.GetOrCreateAsync(cacheKey, async entry =>
        {
            entry.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(10);
            entry.SetSize(1);
            return await client.GetAsync(roundedLatitude, roundedLongitude, cancellationToken);
        }) ?? [];
        return new ForecastResponse(latitude, longitude, clock.UtcNow, DmiCredit.Attribution, points);
    }
}
