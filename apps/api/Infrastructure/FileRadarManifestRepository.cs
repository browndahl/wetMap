using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Options;
using WetMap.Api.Application;
using WetMap.Api.Domain;

namespace WetMap.Api.Infrastructure;

public sealed class FileRadarManifestRepository(IOptions<StorageOptions> options) : IRadarManifestRepository
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<(RadarManifest Manifest, string ETag)> GetAsync(CancellationToken cancellationToken)
    {
        var path = Path.Combine(options.Value.FramesDirectory, "frames.json");
        if (!File.Exists(path))
        {
            return (new RadarManifest(1, DateTimeOffset.UnixEpoch, DmiCredit.Attribution, []), "\"empty\"");
        }
        var bytes = await File.ReadAllBytesAsync(path, cancellationToken);
        var manifest = JsonSerializer.Deserialize<RadarManifest>(bytes, JsonOptions)
            ?? throw new InvalidDataException("frames.json is not a valid radar manifest");
        if (manifest.Attribution != DmiCredit.Attribution)
            throw new InvalidDataException("frames.json does not contain the required DMI attribution");
        return (manifest, $"\"{Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()}\"");
    }
}
