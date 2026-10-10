using System.Net;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

namespace WetMap.Api.Tests;

public sealed class ApiTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;

    public ApiTests(WebApplicationFactory<Program> factory) => _client = factory.CreateClient();

    [Fact]
    public async Task LiveHealthIsAvailable() =>
        Assert.Equal(HttpStatusCode.OK, (await _client.GetAsync("/health/live", TestContext.Current.CancellationToken)).StatusCode);

    [Fact]
    public async Task InvalidCoordinatesUseProblemDetails()
    {
        var response = await _client.GetAsync("/api/v1/weather/forecast?lat=100&lon=10", TestContext.Current.CancellationToken);
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Equal("application/problem+json", response.Content.Headers.ContentType?.MediaType);
    }

    [Fact]
    public async Task EmptyManifestStillHasDmiAttribution()
    {
        var response = await _client.GetAsync("/api/v1/radar/frames", TestContext.Current.CancellationToken);
        response.EnsureSuccessStatusCode();
        Assert.Equal("Baseret på data fra DMI og efterfølgende bearbejdet", response.Headers.GetValues("X-DMI-Attribution").Single());
    }
}
