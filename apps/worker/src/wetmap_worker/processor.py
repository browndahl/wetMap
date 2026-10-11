from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, transform_bounds


@dataclass(frozen=True)
class ProcessedRaster:
    bounds: list[float]
    product: str
    unit: str
    sha256: str


STOPS = np.asarray([-10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0], dtype=np.float32)
COLORS = np.asarray(
    [
        [119, 244, 255],
        [49, 185, 244],
        [52, 120, 229],
        [86, 212, 108],
        [242, 219, 76],
        [255, 139, 56],
        [237, 62, 87],
    ],
    dtype=np.float32,
)


def _attribute(group: h5py.Group, name: str):
    value = group.attrs[name]
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray) and value.size == 1:
        return value.item()
    return value


def inspect_odim(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as source:
        what = source["what"]
        where = source["where"]
        data_group = source["dataset1/data1"]
        array = data_group["data"]
        return {
            "conventions": _attribute(source, "Conventions"),
            "quantity": _attribute(data_group, "quantity"),
            "product": _attribute(what, "product"),
            "gain": float(_attribute(what, "gain")),
            "offset": float(_attribute(what, "offset")),
            "nodata": int(_attribute(what, "nodata")),
            "undetect": int(_attribute(what, "undetect")),
            "projection": _attribute(where, "projdef"),
            "xscale": float(_attribute(where, "xscale")),
            "yscale": float(_attribute(where, "yscale")),
            "shape": list(array.shape),
        }


def _colorize(values: np.ndarray, detected: np.ndarray, coverage: np.ndarray) -> np.ndarray:
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    for channel in range(3):
        rgba[..., channel] = np.interp(values, STOPS, COLORS[:, channel]).astype(np.uint8)
    # Alpha 0 means no coverage and alpha 1 means valid coverage without an echo.
    # Visible echoes encode -10..50 dBZ monotonically as alpha 45..220. We clip
    # weaker detections to -10 dBZ because they are below the public map legend.
    rgba[..., 3] = np.where(
        detected,
        np.clip(45 + (values + 10) * (175 / 60), 45, 220),
        np.where(coverage, 1, 0),
    ).astype(np.uint8)
    rgba[~detected, :3] = 0
    return rgba


def process_hdf5(source_path: Path, output_path: Path) -> ProcessedRaster:
    with h5py.File(source_path, "r") as source:
        if _attribute(source, "Conventions") != "ODIM_H5/V2_0":
            raise ValueError("Unsupported ODIM convention")
        what = source["what"]
        where = source["where"]
        data_group = source["dataset1/data1"]
        quantity = str(_attribute(data_group, "quantity"))
        product = str(_attribute(what, "product"))
        if quantity != "DBZH" or product != "DBZH":
            raise ValueError(
                f"Expected DBZH reflectivity, received quantity={quantity}, product={product}"
            )

        raw = data_group["data"][...]
        nodata = int(_attribute(what, "nodata"))
        undetect = int(_attribute(what, "undetect"))
        gain = float(_attribute(what, "gain"))
        offset = float(_attribute(what, "offset"))
        detected = (raw != nodata) & (raw != undetect)
        coverage = raw != nodata
        dbzh = raw.astype(np.float32) * gain + offset

        source_crs = CRS.from_proj4(str(_attribute(where, "projdef")))
        target_crs = CRS.from_epsg(3857)
        xscale = float(_attribute(where, "xscale"))
        yscale = float(_attribute(where, "yscale"))
        upper_left_lon = float(_attribute(where, "UL_lon"))
        upper_left_lat = float(_attribute(where, "UL_lat"))
        transformer = Transformer.from_crs(CRS.from_epsg(4326), source_crs, always_xy=True)
        upper_left_x, upper_left_y = transformer.transform(upper_left_lon, upper_left_lat)
        # ODIM corner attributes identify outer pixel centres, so expand by half a pixel.
        source_transform = from_origin(
            upper_left_x - xscale / 2,
            upper_left_y + yscale / 2,
            xscale,
            yscale,
        )
        height, width = raw.shape
        left = upper_left_x - xscale / 2
        top = upper_left_y + yscale / 2
        right = left + width * xscale
        bottom = top - height * yscale
        target_transform, target_width, target_height = calculate_default_transform(
            source_crs, target_crs, width, height, left, bottom, right, top
        )
        target_values = np.full((target_height, target_width), -32.0, dtype=np.float32)
        target_detected = np.zeros((target_height, target_width), dtype=np.uint8)
        target_coverage = np.zeros((target_height, target_width), dtype=np.uint8)
        reproject(
            dbzh,
            target_values,
            src_transform=source_transform,
            src_crs=source_crs,
            dst_transform=target_transform,
            dst_crs=target_crs,
            src_nodata=None,
            dst_nodata=-32.0,
            resampling=Resampling.bilinear,
        )
        reproject(
            detected.astype(np.uint8),
            target_detected,
            src_transform=source_transform,
            src_crs=source_crs,
            dst_transform=target_transform,
            dst_crs=target_crs,
            resampling=Resampling.nearest,
        )
        reproject(
            coverage.astype(np.uint8),
            target_coverage,
            src_transform=source_transform,
            src_crs=source_crs,
            dst_transform=target_transform,
            dst_crs=target_crs,
            resampling=Resampling.nearest,
        )
        rgba = _colorize(
            target_values,
            target_detected.astype(bool),
            target_coverage.astype(bool),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgba).save(output_path, "WEBP", lossless=True, method=6)
        west, south, east, north = transform_bounds(
            source_crs, "EPSG:4326", left, bottom, right, top, densify_pts=21
        )
        digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
        return ProcessedRaster([west, south, east, north], product, "dBZ", digest)
