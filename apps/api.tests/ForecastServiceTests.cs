using Microsoft.Extensions.Caching.Memory;
using WetMap.Api.Application;
using WetMap.Api.Domain;
using Xunit;

namespace WetMap.Api.Tests;

public sealed class ForecastServiceTests
{
    private static readonly DateTimeOffset Now = new(2026, 10, 10, 21, 38, 0, TimeSpan.Zero);

    [Fact]
    public async Task ReturnsCurrentAndFutureHoursOnly()
    {
        var points = new[]
        {
            Point(Now.AddHours(-1)),
            Point(new DateTimeOffset(2026, 10, 10, 21, 0, 0, TimeSpan.Zero)),
            Point(Now.AddHours(1))
        };
        using var cache = new MemoryCache(new MemoryCacheOptions());
        var service = new ForecastService(new StubClient(points), cache, new FixedClock(Now));

        var result = await service.GetAsync(56.16, 10.20, TestContext.Current.CancellationToken);

        Assert.Equal(2, result.Points.Count);
        Assert.All(result.Points, point => Assert.True(point.Step >= new DateTimeOffset(2026, 10, 10, 21, 0, 0, TimeSpan.Zero)));
    }

    [Fact]
    public async Task NormalizesDmiNetworkFailures()
    {
        using var cache = new MemoryCache(new MemoryCacheOptions());
        var service = new ForecastService(new StubClient(error: new HttpRequestException("rate limited")), cache, new FixedClock(Now));

        await Assert.ThrowsAsync<ForecastUnavailableException>(() =>
            service.GetAsync(56.16, 10.20, TestContext.Current.CancellationToken));
    }

    private static ForecastPoint Point(DateTimeOffset step) => new(step, 10, 0, 3, 50);

    private sealed class FixedClock(DateTimeOffset now) : IClock
    {
        public DateTimeOffset UtcNow => now;
    }

    private sealed class StubClient(
        IReadOnlyList<ForecastPoint>? points = null,
        Exception? error = null) : IDmiForecastClient
    {
        public Task<IReadOnlyList<ForecastPoint>> GetAsync(
            double latitude,
            double longitude,
            CancellationToken cancellationToken) =>
            error is null
                ? Task.FromResult(points ?? (IReadOnlyList<ForecastPoint>)[])
                : Task.FromException<IReadOnlyList<ForecastPoint>>(error);
    }
}
