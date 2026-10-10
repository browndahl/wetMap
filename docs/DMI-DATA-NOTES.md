# DMI radar data notes

## Live inspection, 2026-10-10

The implementation was based on a real file, not the illustrative document. Metadata request:

```text
GET https://opendataapi.dmi.dk/v1/radardata/collections/composite/items?limit=1&sortorder=datetime,DESC
```

Inspected asset: `dk.com.202610101945.500_max.h5` (observation `2026-10-10T19:45:00Z`, created `19:52:05.609Z`, scan type `doppler`). API STAC bbox: `[4.3790827005, 52.2942720643, 20.7351401749, 59.8277084278]`.

| Field | Observed value |
|---|---|
| Root `Conventions` | `ODIM_H5/V2_0` |
| Data | `dataset1/data1/data`, shape `(1728, 1984)`, `uint8` |
| Quantity / product | `DBZH` / `DBZH` |
| Calibration | `physical dBZ = raw × 0.5 - 32.0` |
| Missing values | `nodata=255`, `undetect=0` |
| Projection | `+proj=stere +ellps=WGS84 +lat_0=56 +lon_0=10.5666 +lat_ts=56` |
| Pixel scale | 500 m × 500 m |
| Upper-left pixel centre | lon 3°, lat 60° → x −422114.801, y 469381.013 m |
| Lower-right pixel centre | lon 18.89328087°, lat 52.15916121° → x 569385.199, y −394118.987 m |
| Z-R metadata | `zr-a=200`, `zr-b=1.6` |

The file contained 2,702,970 nodata pixels, 600,924 undetect pixels, and 124,458 detected pixels. Detected raw values ranged 1–161, or −31.5–48.5 dBZ. The 5th/50th/95th detected percentiles were −3.5/17.0/34.5 dBZ.

## Interpretation and processing

- The visualized measurement is horizontal radar reflectivity (`DBZH`) in dBZ.
- `zr-a` and `zr-b` describe a Z–R relationship, but applying it would add meteorological assumptions and uncertainty. v1 therefore **does not report mm/h**.
- Corner attributes match pixel centres: the projected UL→UR span is 991,500 m = 1,983 intervals × 500 m; UL→LL is 863,500 m = 1,727 intervals × 500 m. The source affine transform expands a half-pixel around those centres.
- The worker converts calibrated values to a colorblind-conscious discrete/interpolated scale, makes nodata/undetect transparent, reprojects the raster to EPSG:3857, and records WGS84 bounds for MapLibre's image source.
- Bilinear resampling is used for dBZ values; a separately nearest-neighbour-resampled validity mask prevents interpolation into missing regions.

## Known limitations

- A single 500 m composite cannot promise street-level precipitation accuracy.
- Radar blockage, attenuation, anomalous propagation, bright band, and composite mosaicking can affect echoes.
- DMI can repopulate/change historical data and provides data “as is”.
- The inspected schema is contract-tested, but the worker fails closed on a changed convention/product rather than silently mislabelling values.

Sources: [DMI Radar Data API](https://www.dmi.dk/friedata/dokumentation/radar-data-api), [DMI terms and CC BY 4.0](https://www.dmi.dk/friedata/dokumentation/terms-of-use).
