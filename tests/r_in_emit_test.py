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


# A region across the antimeridian, as g.region -b reports it over Fiji
# (UTM 60S): west is greater than east.
FIJI = (179.8, -17.2, -178.3, -16.7)


def footprint(title, lonlat):
    """A granule with a CMR footprint polygon ("lat lon lat lon ...")."""
    ring = " ".join(f"{lat} {lon}" for lon, lat in lonlat)
    return granule(title, "2024-06-01T00:00:00.000Z", 0) | {"polygons": [[ring]]}


# A swath crossing the antimeridian over Fiji, and one far to the west.
ACROSS = footprint(
    "EMIT_L2A_RFL_001_20240601T000000_1",
    [(179.5, -17.5), (-178.0, -17.5), (-178.0, -16.5), (179.5, -16.5), (179.5, -17.5)],
)
WEST = footprint(
    "EMIT_L2A_RFL_001_20240601T000100_2",
    [(170.0, -17.5), (171.0, -17.5), (171.0, -16.5), (170.0, -16.5), (170.0, -17.5)],
)


def test_lon_boxes_split_across_antimeridian(emit):
    assert emit.lon_boxes((4.0, 50.8, 4.1, 50.9)) == [(4.0, 50.8, 4.1, 50.9)]
    assert emit.lon_boxes(FIJI) == [(179.8, -17.2, 180.0, -16.7), (-180.0, -17.2, -178.3, -16.7)]


def test_footprint_across_antimeridian(emit):
    pytest.importorskip("shapely")
    kept = emit._filter_by_true_footprint([ACROSS, WEST], FIJI)
    assert [g["title"] for g in kept] == [ACROSS["title"]]
    # A region away from 180 degrees must not match a swath that crosses it.
    kept = emit._filter_by_true_footprint([ACROSS], (10.0, -17.2, 11.0, -16.7))
    assert kept == []


def test_cmr_searched_twice_across_antimeridian(emit, monkeypatch):
    boxes = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(url, timeout=None):
        boxes.append(url.split("bounding_box=")[1].split("&")[0])
        return Response(json.dumps({"feed": {"entry": []}}).encode())

    monkeypatch.setattr(emit.urllib.request, "urlopen", urlopen)
    emit.fetch_granules("EMITL2ARFL", FIJI, "a", "b")
    assert boxes == [
        "179.800000,-17.200000,180.000000,-16.700000",
        "-180.000000,-17.200000,-178.300000,-16.700000",
    ]


MUTSAMUDU = (44.29, -12.29, 44.56, -12.02)


def new_project_region(emit, tmp_path, epsg, bbox):
    import grass.script as gs

    gs.create_project(path=tmp_path, name=f"p{epsg}", epsg=epsg)
    gisrc, env = gs.create_environment(tmp_path, f"p{epsg}", "PERMANENT")
    try:
        emit.narrow_new_project_region(env, bbox)
        return gs.parse_command("g.region", flags="g", env=env)
    finally:
        import os

        os.remove(gisrc)


def test_new_geographic_project_region(emit, tmp_path):
    reg = new_project_region(emit, tmp_path, 4326, MUTSAMUDU)
    assert float(reg["w"]) == pytest.approx(44.29, abs=1e-3)
    assert float(reg["n"]) == pytest.approx(-12.02, abs=1e-3)


def test_new_projected_project_region(emit, tmp_path):
    # UTM 38S: the region must be in metres around Mutsamudu, not degrees.
    reg = new_project_region(emit, tmp_path, 32738, MUTSAMUDU)
    assert 410000 < float(reg["w"]) < float(reg["e"]) < 470000
    assert 8630000 < float(reg["s"]) < float(reg["n"]) < 8680000
    assert float(reg["nsres"]) == 60.0
