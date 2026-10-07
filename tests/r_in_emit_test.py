"""Offline tests of r.in.emit's CMR granule filtering.

CMR is replaced by a fake response, so no network or Earthdata token is
needed. Run inside a GRASS session (gs.verbose needs one), e.g.:

    grass --tmp-project XY --exec python3 -m pytest tests
"""

import importlib.util
import io
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parent.parent / "r.in.emit.py"


@pytest.fixture(scope="module")
def emit():
    spec = importlib.util.spec_from_file_location("r_in_emit", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def granule(title, time_start, cloud):
    # No 'polygons' key: the true-footprint check then keeps the granule.
    return {"title": title, "time_start": time_start, "cloud_cover": str(cloud)}


# Real pairs from CMR over Ninove, Belgium (EMITL2ARFL, 2023): the V001 and
# V002 granules of one acquisition share time_start but not cloud cover.
V1_0403 = granule(
    "EMIT_L2A_RFL_001_20230403T143443_2309310_003", "2023-04-03T14:34:43.000Z", 15
)
V2_0403 = granule("EMIT_L2A_RFL_002_20230403T143443", "2023-04-03T14:34:43.000Z", 0)
V1_0617 = granule(
    "EMIT_L2A_RFL_001_20230617T110003_2316807_005", "2023-06-17T11:00:03.000Z", 64
)
V2_0617 = granule("EMIT_L2A_RFL_002_20230617T110003", "2023-06-17T11:00:03.000Z", 100)
V1_ONLY = granule(
    "EMIT_L2A_RFL_001_20231007T123003_2328008_003", "2023-10-07T12:30:03.000Z", 16
)


@pytest.fixture
def fake_cmr(emit, monkeypatch):
    """Serve the given entries as a single CMR page."""

    def install(entries):
        def urlopen(url, timeout=None):
            return io.BytesIO(json.dumps({"feed": {"entry": entries}}).encode())

        monkeypatch.setattr(emit.urllib.request, "urlopen", urlopen)

    return install


def fetch(emit, **kwargs):
    return emit.fetch_granules(
        "EMITL2ARFL", (4.0, 50.8, 4.1, 50.9), "2023-01-01", "2023-12-31", **kwargs
    )


def test_latest_versions_keeps_newest_per_acquisition(emit):
    kept = emit.latest_versions([V1_ONLY, V1_0403, V2_0403])
    assert [g["title"] for g in kept] == [V2_0403["title"], V1_ONLY["title"]]


def test_reflectance_versions_deduplicated(emit, fake_cmr):
    fake_cmr([V1_0403, V2_0403, V1_ONLY])
    titles = [g["title"] for g in fetch(emit)]
    assert titles == [V2_0403["title"], V1_ONLY["title"]]


def test_version_filter_runs_before_cloud_filter(emit, fake_cmr):
    # V001 of 2023-06-17 passes clouds=70 but is superseded by a cloudy V002:
    # the acquisition must drop out, not fall back to the old version.
    fake_cmr([V1_0617, V2_0617, V1_ONLY])
    titles = [g["title"] for g in fetch(emit, clouds=70)]
    assert titles == [V1_ONLY["title"]]


def test_newest_version_used_for_cloud_cover(emit, fake_cmr):
    # V001 reports 15 %, V002 0 %: clouds=10 keeps the acquisition (as V002).
    fake_cmr([V1_0403, V2_0403])
    titles = [g["title"] for g in fetch(emit, clouds=10)]
    assert titles == [V2_0403["title"]]


def test_plumes_not_deduplicated(emit, fake_cmr):
    # Two plume complexes of one overpass share time_start.
    t = "2024-08-25T06:44:23.000Z"
    plumes = [
        granule("EMIT_L2B_CH4PLM_001_20240825T064423_003501", t, 5),
        granule("EMIT_L2B_CH4PLM_001_20240825T064423_003502", t, 5),
    ]
    fake_cmr(plumes)
    assert len(fetch(emit, newest_only=False)) == 2


def test_map_names_unique_after_filter(emit, fake_cmr):
    # Map names are built from the acquisition time: they must not collide.
    fake_cmr([V1_0403, V2_0403, V1_0617, V2_0617, V1_ONLY])
    stamps = [emit.granule_datetime(g).strftime("%Y%m%dT%H%M%S") for g in fetch(emit)]
    assert len(stamps) == len(set(stamps))
