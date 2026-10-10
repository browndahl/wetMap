from pathlib import Path

import h5py
import numpy as np
from PIL import Image

from wetmap_worker.processor import inspect_odim, process_hdf5


def make_fixture(path: Path) -> None:
    with h5py.File(path, "w") as target:
        target.attrs["Conventions"] = "ODIM_H5/V2_0"
        what = target.create_group("what")
        what.attrs.update({"product": "DBZH", "gain": 0.5, "offset": -32.0, "nodata": 255, "undetect": 0})
        where = target.create_group("where")
        where.attrs.update(
            {
                "projdef": "+proj=stere +ellps=WGS84 +lat_0=56 +lon_0=10.5666 +lat_ts=56",
                "xscale": 500,
                "yscale": 500,
                "UL_lon": [3.0],
                "UL_lat": [60.0],
            }
        )
        data_group = target.create_group("dataset1/data1")
        data_group.attrs["quantity"] = "DBZH"
        data_group.create_dataset("data", data=np.asarray([[0, 64, 100], [255, 120, 150]], dtype=np.uint8))


def test_inspects_verified_odim_fields(tmp_path: Path) -> None:
    fixture = tmp_path / "radar.h5"
    make_fixture(fixture)
    result = inspect_odim(fixture)
    assert result["quantity"] == "DBZH"
    assert result["gain"] == 0.5
    assert result["offset"] == -32.0


def test_outputs_transparent_georeferenced_webp(tmp_path: Path) -> None:
    fixture = tmp_path / "radar.h5"
    output = tmp_path / "radar.webp"
    make_fixture(fixture)
    result = process_hdf5(fixture, output)
    image = Image.open(output)
    assert image.mode == "RGBA"
    assert result.product == "DBZH"
    assert result.unit == "dBZ"
    assert len(result.sha256) == 64
    assert result.bounds[0] < result.bounds[2]
