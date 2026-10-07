## DESCRIPTION

*r.in.emit* downloads NASA **EMIT** (Earth Surface Mineral Dust Source
Investigation) L2A Estimated Surface Reflectance granules directly into
the current GRASS GIS mapset, or a brand new GRASS project/location, by
querying **NASA's Common Metadata Repository (CMR)** and fetching
matching granules straight from **LP DAAC** (no STAC cube service is
involved — EMIT granules are downloaded whole, as delivered, not cropped
to the region like *r.in.sentinel*'s `cubo`-based Sentinel-2 cubes).

Instead of reflectance, it can also fetch EMIT L1B at-sensor radiance
(**-r**) and the EMIT L2B greenhouse gas products for methane (**-m**)
and carbon dioxide (**-c**).

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

### Greenhouse gas products (-m, -c)

**-m** (methane, CH4) and **-c** (carbon dioxide, CO2) switch the module
from reflectance to the EMIT L2B greenhouse gas collections. Both flags
can be given together. **gas_products=** selects which products are
fetched for each gas (both by default):

- **enhancement**: one granule per scene (`EMITL2BCH4ENH`,
  `EMITL2BCO2ENH`), holding three single-band GeoTIFFs: the enhancement
  itself (`ENH`, in ppm m), its sensitivity (`SENS`) and its uncertainty
  (`UNCERT`).
- **plumes**: one granule per detected plume complex (`EMITL2BCH4PLM`,
  `EMITL2BCO2PLM`), holding a single-band GeoTIFF of the plume and a
  GeoJSON outline (`PLMMETA`) carrying the plume attributes (plume ID,
  maximum concentration and its location, and the emission rate
  estimate with its uncertainty when one was made).

**short_name=** is ignored with **-m**/**-c**. Gas files are small
(a few tens of MB per enhancement scene, tens of kB per plume) compared
with reflectance granules.

**clouds=** filters enhancement scenes only. A plume complex exists only
where the retrieval already found enough clear pixels to detect it, and
its CMR cloud cover describes the whole scene rather than the plume.

With **-i**, every GeoTIFF is imported with *r.import* as an ordinary 2D
raster map, not a raster_3d cube, since each holds a single band.
Enhancement layers span the whole ~75 km swath and are cropped to the
current region (`extent=region`); plume rasters are kept whole so that
no plume is cut at the region edge. Each plume outline is imported with
*v.import* as a vector map, with the plume attributes in its attribute
table. Rasters get their acquisition time with *r.timestamp* and plume
vectors with *v.timestamp*. Map names are
`{output}_{layer}_{acquisition timestamp}`, where the layer is `ch4enh`,
`ch4sens`, `ch4uncert` or `ch4plm` (`co2...` for carbon dioxide). Plume
maps also end with the plume ID, since one overpass can detect several
plumes, e.g. `uae_ch4plm_20240825T064423_003501`; a plume's raster and
vector maps share the same name.

With **strds=**, one space-time raster dataset (strds) is created per
imported layer, named `{strds}_{layer}`, e.g. `uae_ch4enh` and
`uae_ch4plm`.

### L1B radiance (-r)

**-r** downloads EMIT L1B at-sensor radiance (`EMITL1BRAD`) instead of
reflectance, for processing that starts from radiance, such as methane
matched-filter retrievals with *i.hyper.methane*. Each granule holds two
NetCDF files, both downloaded: the radiance (`RAD`) and the observation
geometry (`OBS`: solar and view angles and path length). **-r** can be
combined with **-m**/**-c** in the same run.

As for reflectance, only the newest collection version of each
acquisition is downloaded (see *Collection versions* below).

With **-i**, each radiance file is imported as a raster_3d cube by
*i.hyper.import* with its **-r** flag, which reads only the part of the
swath covering the current region (a full L1B scene needs more than
11 GB of memory to import). Map names are `{output}_rad_{acquisition
timestamp}`, and **strds=** creates a str3ds named `{strds}_rad`. The OBS
file is downloaded but not imported. This needs an *i.hyper.import* whose
EMIT reader imports L1B radiance and has the **-r** flag; with an older
one, **-r** together with **-i** stops with an error before any download
starts.

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

### Collection versions

EMIT L1B radiance and L2A reflectance are being reprocessed from
collection version V001 to V002, and CMR returns both versions of an
acquisition when both exist (V002 granule names also drop the orbit and
scene suffix, e.g. `EMIT_L2A_RFL_002_20230403T143443` next to
`EMIT_L2A_RFL_001_20230403T143443_2309310_003`). Only the newest version
of each acquisition is listed and downloaded, for reflectance, radiance
and gas enhancement scenes alike. Without this, the same multi-GB scene
was downloaded twice and both copies got the same map name, so only one
of them was imported. Plume complexes are not filtered by version, since
several plumes share one acquisition time.

The version filter runs before **clouds=**: the versions of one
acquisition report different cloud cover (0 % for V002 and 15 % for V001
on 2023-04-03 over Ninove, Belgium), and the newest is the reference.

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

For reflectance, **-i** runs [i.hyper.import](i.hyper.import.md)
(`product=emit`) on every downloaded granule (gas products are imported
differently, see above), producing one raster_3d hyperspectral cube per
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

### List methane products and L1B radiance over a site

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65
r.in.emit start=2024-08-20 end=2024-08-31 -m -r -l
```

```text
Available granules:
2024-08-25T06:44:23+00:00  EMITL1BRAD  cloud_cover=46%  EMIT_L1B_RAD_001_20240825T064423_2423804_027  (2 files)
2024-08-25T06:44:23+00:00  EMITL2BCH4ENH  cloud_cover=46%  EMIT_L2B_CH4ENH_002_20240825T064423_2423804_027  (3 files)
2024-08-25T06:44:23+00:00  EMITL2BCH4PLM  cloud_cover=0%  EMIT_L2B_CH4PLM_002_20240825T064423_003501  (2 files)
```

### Download and import methane enhancement and plumes

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65
r.in.emit start=2024-08-25 end=2024-08-25 output=uae -m -i strds=uae
g.list type=raster,vector pattern="uae_*"
v.db.select map=uae_ch4plm_20240825T064423_003501
```

### Download only the detected plume complexes for methane and CO2

```sh
r.in.emit start=2023-01-01 end=2024-12-31 output=uae -m -c \
  gas_products=plumes -i
```

### Download and import L1B radiance for i.hyper.methane

```sh
g.region n=25.36 s=25.26 e=55.75 w=55.60
r.in.emit start=2024-08-25 end=2024-08-25 output=uae -r -i
```

### Print the resolved search bounding box only

```sh
g.region n=25.34 s=25.30 e=55.72 w=55.65
r.in.emit start=2024-01-01 end=2024-12-31 -p
```

## SEE ALSO

*[g.proj](g.proj.md), [g.region](g.region.md),
[i.hyper.import](i.hyper.import.md), [i.hyper.methane](i.hyper.methane.md),
[r.import](r.import.md), [r.in.sentinel](r.in.sentinel.md),
[r.timestamp](r.timestamp.md), [r3.timestamp](r3.timestamp.md),
[t.create](t.create.md), [t.register](t.register.md),
[v.import](v.import.md), [v.timestamp](v.timestamp.md)*

## REFERENCES

- Green, R.O. et al. (2020). *The Earth Surface Mineral Dust Source
  Investigation (EMIT).* IEEE Aerospace Conference.
- [EMIT project site (JPL)](https://earth.jpl.nasa.gov/emit/)
- [NASA CMR API documentation](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html)
- [LP DAAC EMIT L2A RFL product page](https://lpdaac.usgs.gov/products/emitl2arflv001/)
- Thorpe, A.K. et al. (2023). *Attribution of individual methane and
  carbon dioxide emission sources using EMIT observations from space.*
  Science Advances 9. [doi:10.1126/sciadv.adh2391](https://doi.org/10.1126/sciadv.adh2391)
- EMIT L2B product DOIs:
  [CH4 enhancement](https://doi.org/10.5067/EMIT/EMITL2BCH4ENH.002),
  [CH4 plume complexes](https://doi.org/10.5067/EMIT/EMITL2BCH4PLM.002),
  [CO2 enhancement](https://doi.org/10.5067/EMIT/EMITL2BCO2ENH.002),
  [CO2 plume complexes](https://doi.org/10.5067/EMIT/EMITL2BCO2PLM.002)

## AUTHOR

Yann Chemin
