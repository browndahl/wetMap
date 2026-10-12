using System.Globalization;
using System.Text.Json;
using WetMap.Api.Application;
using WetMap.Api.Domain;

namespace WetMap.Api.Infrastructure;

public sealed class DmiForecastClient(HttpClient httpClient, ILogger<DmiForecastClient> logger) : IDmiForecastClient
{
    public async Task<IReadOnlyList<ForecastPoint>> GetAsync(double latitude, double longitude, CancellationToken cancellationToken)
    {
        var point = FormattableString.Invariant($"POINT({longitude:F5} {latitude:F5})");
        var query = new Dictionary<string, string?>
        {
            ["coords"] = point,
            ["crs"] = "crs84",
            ["parameter-name"] = "temperature-2m,wind-speed-10m,total-precipitation,fraction-of-cloud-cover",
            ["f"] = "GeoJSON"
        };
        var url = "/v1/forecastedr/collections/harmonie_dini_sf/position?" +
            string.Join("&", query.Select(item => $"{Uri.EscapeDataString(item.Key)}={Uri.EscapeDataString(item.Value!)}"));
        using var response = await httpClient.GetAsync(url, cancellationToken);
        response.EnsureSuccessStatusCode();
        await using var content = await response.Content.ReadAsStreamAsync(cancellationToken);
        using var document = await JsonDocument.ParseAsync(content, cancellationToken: cancellationToken);
        var result = new List<ForecastPoint>();
        foreach (var feature in document.RootElement.GetProperty("features").EnumerateArray())
        {
            var properties = feature.GetProperty("properties");
            if (!properties.TryGetProperty("step", out var stepElement) ||
                !DateTimeOffset.TryParse(stepElement.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var step))
                continue;
            result.Add(new ForecastPoint(
                step,
                KelvinToCelsius(Number(properties, "temperature-2m")),
                Number(properties, "total-precipitation"),
                Number(properties, "wind-speed-10m"),
                FractionToPercent(Number(properties, "fraction-of-cloud-cover"))));
        }
        var previousAccumulation = 0d;
        var normalized = result
            .OrderBy(pointResult => pointResult.Step)
            .Select(pointResult =>
            {
                if (pointResult.PrecipitationKgM2 is not { } accumulated)
                    return pointResult;
                var intervalAmount = Math.Round(Math.Max(0, accumulated - previousAccumulation), 3);
                previousAccumulation = accumulated;
                return pointResult with { PrecipitationKgM2 = intervalAmount };
            })
            .Take(48)
            .ToArray();
        logger.LogInformation("Fetched {PointCount} DMI forecast points", normalized.Length);
        return normalized;
    }

    private static double? Number(JsonElement properties, string name) =>
        properties.TryGetProperty(name, out var element) && element.ValueKind == JsonValueKind.Number
            ? element.GetDouble()
            : null;

    private static double? KelvinToCelsius(double? kelvin) => kelvin is null ? null : Math.Round(kelvin.Value - 273.15, 1);
    private static double? FractionToPercent(double? fraction) => fraction is null ? null : Math.Round(fraction.Value * 100, 0);
}
