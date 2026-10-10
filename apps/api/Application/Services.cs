using Microsoft.Extensions.Caching.Memory;
using Polly.Timeout;
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
        var staleCacheKey = $"{cacheKey}:stale";
        IReadOnlyList<ForecastPoint> points;
        if (!cache.TryGetValue(cacheKey, out points!))
        {
            try
            {
                points = await client.GetAsync(roundedLatitude, roundedLongitude, cancellationToken);
                cache.Set(cacheKey, points, new MemoryCacheEntryOptions()
                    .SetAbsoluteExpiration(TimeSpan.FromMinutes(10))
                    .SetSize(1));
                cache.Set(staleCacheKey, points, new MemoryCacheEntryOptions()
                    .SetAbsoluteExpiration(TimeSpan.FromHours(6))
                    .SetSize(1));
            }
            catch (Exception error) when (
                !cancellationToken.IsCancellationRequested &&
                error is (HttpRequestException or TaskCanceledException or TimeoutRejectedException))
            {
                if (!cache.TryGetValue(staleCacheKey, out points!))
                    throw new ForecastUnavailableException("DMI forecast data is temporarily unavailable.", error);
            }
        }
        var now = clock.UtcNow;
        var currentHour = new DateTimeOffset(
            now.Year,
            now.Month,
            now.Day,
            now.Hour,
            0,
            0,
            TimeSpan.Zero);
        var upcomingPoints = points.Where(point => point.Step >= currentHour).Take(48).ToArray();
        return new ForecastResponse(latitude, longitude, now, DmiCredit.Attribution, upcomingPoints);
    }
}

public sealed class ForecastUnavailableException(string message, Exception innerException)
    : Exception(message, innerException);
