using Microsoft.AspNetCore.Mvc;
using WetMap.Api.Application;
using WetMap.Api.Domain;
using WetMap.Api.Infrastructure;

namespace WetMap.Api.Presentation;

public static class Endpoints
{
    public static IEndpointRouteBuilder MapWetMapEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var api = endpoints.MapGroup("/api/v1").WithTags("WetMap v1");
        api.MapGet("/radar/frames", GetFrames)
            .WithName("GetRadarFrames")
            .Produces<RadarManifest>()
            .Produces(StatusCodes.Status304NotModified)
            .CacheOutput(policy => policy.Expire(TimeSpan.FromSeconds(60)));
        api.MapGet("/weather/forecast", GetForecast)
            .WithName("GetForecast")
            .Produces<ForecastResponse>()
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .CacheOutput("forecast");
        endpoints.MapGet("/frames/{fileName}", GetFrame)
            .WithName("GetRadarFrame")
            .Produces(StatusCodes.Status404NotFound);
        return endpoints;
    }

    private static async Task<IResult> GetFrames(HttpContext context, RadarService service, CancellationToken cancellationToken)
    {
        var (manifest, etag) = await service.GetAsync(cancellationToken);
        context.Response.Headers.ETag = etag;
        context.Response.Headers.CacheControl = "public,max-age=60,stale-while-revalidate=300";
        context.Response.Headers["X-DMI-Attribution"] = DmiCredit.Attribution;
        context.Response.Headers["X-Data-Fetched-At"] = manifest.Frames.LastOrDefault()?.FetchedAt.ToString("O") ?? manifest.GeneratedAt.ToString("O");
        if (context.Request.Headers.IfNoneMatch.Contains(etag)) return Results.StatusCode(StatusCodes.Status304NotModified);
        return Results.Ok(manifest);
    }

    private static async Task<IResult> GetForecast(
        [FromQuery] double lat,
        [FromQuery] double lon,
        ForecastService service,
        CancellationToken cancellationToken)
    {
        if (lat is < -90 or > 90 || lon is < -180 or > 180)
            return Results.Problem(
                statusCode: StatusCodes.Status400BadRequest,
                title: "Invalid coordinates",
                detail: "Latitude must be between -90 and 90 and longitude between -180 and 180.",
                type: "https://wetmap.invalid/problems/invalid-coordinates");
        var result = await service.GetAsync(lat, lon, cancellationToken);
        return Results.Ok(result);
    }

    private static IResult GetFrame(string fileName, Microsoft.Extensions.Options.IOptions<StorageOptions> options)
    {
        if (Path.GetFileName(fileName) != fileName || !fileName.EndsWith(".webp", StringComparison.OrdinalIgnoreCase))
            return Results.NotFound();
        var path = Path.Combine(options.Value.FramesDirectory, fileName);
        return File.Exists(path)
            ? Results.File(path, "image/webp", lastModified: File.GetLastWriteTimeUtc(path), entityTag: new Microsoft.Net.Http.Headers.EntityTagHeaderValue($"\"{Path.GetFileNameWithoutExtension(fileName)}\""), enableRangeProcessing: false)
            : Results.NotFound();
    }
}
