#!/usr/bin/env python3
# Test for r.in.emit
# Requires: GRASS GIS session in a latlong (WGS84) location
# Searches/downloads: Small area over Plumergat (56400), France

import os
import unittest
from pathlib import Path

from grass.gunittest.case import TestCase
from grass.gunittest.main import test

try:
    import netCDF4  # noqa: F401

    HAS_NETCDF4 = True
except ImportError:
    HAS_NETCDF4 = False


def _find_token():
    """Mirror r.in.emit's own token resolution order for test skip checks."""
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if token:
        return token
    token_file = Path(os.environ.get("EMIT_TEST_TOKEN_FILE", "")).expanduser()
    if str(token_file) and token_file.exists():
        return token_file.read_text().strip()
    return ""


HAS_TOKEN = bool(_find_token())
# EMIT granules are large (hundreds of MB to a few GB) -- an actual
# download+import is opt-in, not run by default even when a token is
# available, unlike r.in.sentinel's tiny cubo-cropped test cube.
RUN_DOWNLOAD_TEST = os.environ.get("RUN_EMIT_DOWNLOAD_TEST") == "1"

# Plumergat, Brittany, France — small coastal area, matches r.in.sentinel's
# own test area for consistency across this ecosystem's importers.
PLUMERGAT_N = 47.73
PLUMERGAT_S = 47.68
PLUMERGAT_E = -2.85
PLUMERGAT_W = -2.93


class TestRInEmitSearch(TestCase):
    """Fast, network-only (no download) tests: bounding box + CMR search."""

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        cls.runModule(
            "g.region", n=PLUMERGAT_N, s=PLUMERGAT_S, e=PLUMERGAT_E, w=PLUMERGAT_W
        )

    @classmethod
    def tearDownClass(cls):
        cls.del_temp_region()

    def test_print_bbox(self):
        """-p resolves and prints the search bounding box without downloading."""
        module = self.runModule("r.in.emit", start="2024-01-01", end="2024-01-31", flags="p")
        self.assertEqual(module.returncode, 0)

    def test_list_granules(self):
        """-l queries NASA CMR and lists granules without downloading."""
        # A wide date range over a small area that has repeat EMIT coverage;
        # tolerate zero results (coverage is not guaranteed for every area/
        # period) as long as the module runs and exits cleanly.
        module = self.runModule(
            "r.in.emit", start="2022-01-01", end="2025-12-31", flags="l"
        )
        self.assertEqual(module.returncode, 0)

    def test_bbox_matches_region(self):
        """The bounding box printed by -p reflects the region just set."""
        import grass.script as gs

        out = gs.read_command(
            "r.in.emit", start="2024-01-01", end="2024-01-31", flags="p"
        )
        self.assertIn("west=", out)
        self.assertIn("north=", out)
        # Rough sanity check: printed west/east should bracket Plumergat's
        # own W/E (region is set exactly to those values, so bbox should
        # match closely once round-tripped through g.region -b).
        values = {}
        for tok in out.strip().split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                try:
                    values[k] = float(v)
                except ValueError:
                    pass
        self.assertAlmostEqual(values["west"], PLUMERGAT_W, delta=0.01)
        self.assertAlmostEqual(values["north"], PLUMERGAT_N, delta=0.01)


@unittest.skipUnless(HAS_TOKEN, "no NASA Earthdata token available (EARTHDATA_TOKEN)")
@unittest.skipUnless(
    RUN_DOWNLOAD_TEST,
    "set RUN_EMIT_DOWNLOAD_TEST=1 to opt in to a real (large) EMIT download",
)
class TestRInEmitDownload(TestCase):
    """Real download (and optionally import) tests -- opt-in, since EMIT
    granules are large (hundreds of MB to a few GB), unlike r.in.sentinel's
    small cubo-cropped test cube."""

    output_prefix = "test_emit"

    @classmethod
    def setUpClass(cls):
        cls.use_temp_region()
        cls.runModule(
            "g.region", n=PLUMERGAT_N, s=PLUMERGAT_S, e=PLUMERGAT_E, w=PLUMERGAT_W
        )
        cls.tmp_output_dir = Path(cls.get_tempfile()).parent / "r_in_emit_test_dl"

    @classmethod
    def tearDownClass(cls):
        cls.del_temp_region()
        import grass.script as gs

        mapset = gs.gisenv()["MAPSET"]
        rasters3d = gs.list_grouped("raster_3d").get(mapset, [])
        to_remove = [m for m in rasters3d if m.startswith(cls.output_prefix)]
        if to_remove:
            gs.run_command(
                "g.remove", type="raster_3d", name=",".join(to_remove), flags="f"
            )
        try:
            import grass.temporal as tgis

            tgis.init()
            str3ds_list = gs.read_command(
                "t.list", type="str3ds", columns="name"
            ).strip()
            for line in str3ds_list.splitlines():
                name = line.split("|")[0].strip()
                if name.startswith(cls.output_prefix):
                    gs.run_command("t.remove", flags="rf", inputs=name, type="str3ds")
        except Exception:
            pass

    def test_download_only(self):
        """A real granule download succeeds and leaves a non-empty .nc file."""
        self.assertModule(
            "r.in.emit",
            start="2022-08-01",
            end="2024-12-31",
            output=self.output_prefix,
            output_dir=str(self.tmp_output_dir),
        )
        nc_files = list(self.tmp_output_dir.rglob("*.nc"))
        self.assertGreater(len(nc_files), 0, "No granules were downloaded")
        for f in nc_files:
            self.assertGreater(f.stat().st_size, 0, f"{f} is empty")

    @unittest.skipUnless(HAS_NETCDF4, "netCDF4 not installed (needed by i.hyper.import)")
    def test_download_and_import(self):
        """-i imports a downloaded granule as a raster_3d cube with a timestamp."""
        import grass.script as gs

        prefix = self.output_prefix + "_imp"
        self.assertModule(
            "r.in.emit",
            start="2022-08-01",
            end="2024-12-31",
            output=prefix,
            output_dir=str(self.tmp_output_dir),
            flags="i",
        )
        mapset = gs.gisenv()["MAPSET"]
        cubes = [
            m
            for m in gs.list_grouped("raster_3d").get(mapset, [])
            if m.startswith(prefix)
        ]
        self.assertGreater(len(cubes), 0, "No raster_3d cube imported")

        ts = gs.read_command("r3.timestamp", map=cubes[0]).strip()
        self.assertNotEqual(ts, "none", f"r3.timestamp not set on {cubes[0]}")


if __name__ == "__main__":
    test()
