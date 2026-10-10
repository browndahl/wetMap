using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;

namespace WetMap.Api.Infrastructure;

public sealed class FramesHealthCheck(IOptions<StorageOptions> options) : IHealthCheck
{
    public Task<HealthCheckResult> CheckHealthAsync(HealthCheckContext context, CancellationToken cancellationToken = default)
    {
        var file = new FileInfo(Path.Combine(options.Value.FramesDirectory, "frames.json"));
        if (!file.Exists)
            return Task.FromResult(HealthCheckResult.Degraded("No frames manifest; API remains available."));
        var age = DateTimeOffset.UtcNow - file.LastWriteTimeUtc;
        return Task.FromResult(age > TimeSpan.FromMinutes(20)
            ? HealthCheckResult.Degraded($"Radar manifest is stale ({age.TotalMinutes:F0} minutes).")
            : HealthCheckResult.Healthy());
    }
}
