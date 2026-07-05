## DESCRIPTION

*r.in.emit* downloads NASA **EMIT** (Earth Surface Mineral Dust Source
Investigation) L2A Estimated Surface Reflectance granules directly into
the current GRASS GIS mapset, or a brand new GRASS project/location, by
querying **NASA's Common Metadata Repository (CMR)** and fetching
matching granules straight from **LP DAAC** (no STAC cube service is
involved — EMIT granules are downloaded whole, as delivered, not cropped
to the region like *r.in.sentinel*'s `cubo`-based Sentinel-2 cubes).

Requires a free
[NASA Earthdata](https://urs.earthdata.nasa.gov) account and a Bearer
token (Earthdata login → *User Profile* → *Generate Token*).

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65

r.in.emit start=2024-01-01 end=2024-12-31 clouds=20 \
  output=dubai -i strds=dubai_ts
```

### Default operation: update the current project

By default, downloaded granules (and, with **-i**, imported raster_3d
cubes) go straight into the GRASS project/mapset *r.in.emit* was
launched from — exactly like every other `r.in.*`/`i.in.*` importer, and
consistent with *r.in.sentinel*. No extra options are needed for this,
the module's default operation.

### Optional: create a new project instead

Give **project=** to create a brand new GRASS location (under **dbase=**,
default the current GISDBASE) and import there instead, leaving the
calling session's own project untouched. EMIT L2A reflectance is
delivered already orthorectified onto a WGS84 geographic grid via its
bundled Geolocation Lookup Table (GLT), so the new project defaults to
**epsg=4326** — override only if you have a specific reason to reproject
immediately. If the named project already exists, it is reused (not
recreated) so repeated runs accumulate into the same project. After the
first successful import, the new project's default region is set from
that cube so it starts in a sane state.

### Output naming

Each granule becomes one file (and, with **-i**, one raster_3d map)
named `{output}_{acquisition timestamp}`, e.g.
`emit_20240619T081558` — using the full acquisition timestamp (not just
the date) since a region can have more than one EMIT overpass on the
same calendar day, unlike Sentinel-2's one-scene-per-tile-per-day
cadence that *r.in.sentinel* mosaics.

### The search area

The module always reads the **current** computational region (`g.region`)
of the session it was launched from to determine the CMR search bounding
box — reprojected to WGS84 automatically via `g.region -b`, so this works
identically whether the calling project is itself geographic or
projected. This is true regardless of **project=**: the *search* area
always comes from the calling session's own region, only the *output*
location differs.

## NOTES

### Full-granule downloads, not cropped cubes

Unlike *r.in.sentinel* (which requests an exact bounding-box cube via
`cubo`), EMIT has no equivalent per-request cropping service at LP DAAC
— each matching granule's full reflectance NetCDF file (its actual
flight-line swath extent, several hundred MB to a few GB) is downloaded
as-is. Only the reflectance (`_RFL_`) file is fetched; the companion
uncertainty (`_RFLUNCERT_`) and quality-mask (`_MASK_`) files are skipped
automatically, since *i.hyper.import*'s EMIT reader only needs the
reflectance NetCDF (it carries its own GLT for georeferencing, and its
own per-band `good_wavelengths` validity flags).

Downloaded files are kept in **output_dir** (default
`$HOME/RSDATA/EMIT_<output>`, one subdirectory per acquisition year) and
are *not* re-downloaded on a later run unless `--overwrite` is given —
EMIT granules are large enough that a persistent, skip-if-present local
cache matters far more here than for Sentinel-2 tiles.

### Cloud filtering

**clouds=** filters by each granule's CMR-reported scene cloud-cover
percentage (client-side — the CMR granule search API has no server-side
cloud-cover query parameter for this collection, unlike a spatial/temporal
filter).

### Authentication

A Bearer token is required for every request to LP DAAC's protected data
URLs. Resolved in this order: **token=**, then the `EARTHDATA_TOKEN`
environment variable, then a `TOKEN` file inside **output_dir**. Generate
one at [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov) (*User
Profile* → *Generate Token*) — tokens expire, so expect to refresh this
periodically.

### Importing with i.hyper.import (-i)

**-i** runs [i.hyper.import](i.hyper.import.md) (`product=emit`) on every
downloaded granule, producing one raster_3d hyperspectral cube per
granule in the target project. **composites=**, **composites_custom=**,
**strength=**, and **-n** are simply forwarded to *i.hyper.import* and
only take effect together with **-i**. A granule already imported (a
raster_3d map of the same name already exists) is skipped unless
`--overwrite` is given, mirroring the download cache's own skip
behaviour.

### Timestamp support

Every imported cube gets its real acquisition date/time set via
`r3.timestamp`, read directly from the granule's own CMR `time_start`
metadata — not just the calendar date, since EMIT's flight-line
acquisitions can occur multiple times per day over the same area.

### Space-Time 3D Raster Dataset (STR3DS) support

**strds=** (requires **-i**) creates one **str3ds** — GRASS's temporal
type for a time series of 3D rasters, the raster_3d equivalent of a
STRDS — via `t.create type=str3ds` + `t.register type=raster_3d`,
collecting every cube imported in that run in one time-aware dataset,
ready for `t.rast3d.list`, `t.rast3d.algebra`, or similar temporal-3D
tools.

### Listing and dry-checks

- **-l** — list matching granules (acquisition timestamp, cloud cover,
  filename) and exit, no download.
- **-p** — print the resolved WGS84 search bounding box and exit.

## REQUIREMENTS

```sh
pip install netCDF4
```

(`netCDF4` is required by *i.hyper.import*'s EMIT reader when **-i** is
used; the download step itself has no extra Python dependency beyond the
standard library.)

## EXAMPLES

### Download only, current project, no cloud filter

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65
r.in.emit start=2024-01-01 end=2024-12-31 output=dubai
```

### List available granules without downloading

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65
r.in.emit start=2022-01-01 end=2024-12-31 clouds=20 -l
```

```text
Available granules:
2023-07-27T10:02:31+00:00  cloud_cover=10%  EMIT_L2A_RFL_001_20230727T100231_2320807_026.nc
2023-07-31T08:26:09+00:00  cloud_cover=13%  EMIT_L2A_RFL_001_20230731T082609_2321206_020.nc
2024-06-21T08:27:46+00:00  cloud_cover=5%   EMIT_L2A_RFL_001_20240621T082746_2417306_048.nc
2024-07-23T10:40:33+00:00  cloud_cover=11%  EMIT_L2A_RFL_001_20240723T104033_2420507_022.nc
```

### Download and import into the current project, with a STR3DS

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65
r.in.emit start=2024-01-01 end=2024-12-31 clouds=30 \
  output=dubai -i strds=dubai_ts composites=rgb,swir_geology
t.rast3d.list input=dubai_ts
```

### Create a brand new project for the imported cubes

```sh
r.in.emit start=2024-01-01 end=2024-12-31 output=dubai \
  -i project=emit_dubai_new dbase=$HOME/grassdata
```

### Print the resolved search bounding box only

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65
r.in.emit start=2024-01-01 end=2024-12-31 -p
```

## SEE ALSO

*[i.hyper.import](i.hyper.import.md), [r.in.sentinel](r.in.sentinel.md),
[r3.timestamp](r3.timestamp.md), [t.create](t.create.md),
[t.register](t.register.md), [g.region](g.region.md),
[g.proj](g.proj.md)*

## REFERENCES

- Green, R.O. et al. (2020). *The Earth Surface Mineral Dust Source
  Investigation (EMIT).* IEEE Aerospace Conference.
- [EMIT project site (JPL)](https://earth.jpl.nasa.gov/emit/)
- [NASA CMR API documentation](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html)
- [LP DAAC EMIT L2A RFL product page](https://lpdaac.usgs.gov/products/emitl2arflv001/)

## AUTHOR

Yann Chemin
