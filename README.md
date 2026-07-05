# r.in.emit

A [GRASS GIS](https://grass.osgeo.org/) addon that downloads NASA
**EMIT** hyperspectral imagery (L2A Estimated Surface Reflectance)
straight from **NASA CMR / LP DAAC** into the current mapset — or a
brand new GRASS project — and optionally imports each granule as a
raster_3d hyperspectral cube via
[i.hyper.import](https://github.com/YannChemin/i.hyper.import).

```
g.region n=25.34 s=25.30 e=55.72 w=55.65

r.in.emit start=2024-01-01 end=2024-12-31 clouds=20 \
  output=dubai -i strds=dubai_ts
```

## Why

[r.in.sentinel](https://github.com/YannChemin/r.in.sentinel) closes the
account-free Sentinel-2 gap in this no-API-key ecosystem
([t.in.era5](https://github.com/YannChemin/t.in.era5),
[r.in.dem](https://github.com/YannChemin/r.in.dem)); this module does
the equivalent for NASA's EMIT imaging spectrometer — the highest
publicly-available spectral resolution optical dataset with global
coverage, and the standard direct input to the `i.hyper.*` hyperspectral
module family
([i.hyper.import](https://github.com/YannChemin/i.hyper.import),
[i.hyper.endmembers](https://github.com/YannChemin/i.hyper.endmembers),
[i.hyper.speclookup](https://github.com/YannChemin/i.hyper.speclookup)).

## How it works

Unlike *r.in.sentinel*'s `cubo`-based exact bounding-box cube requests,
EMIT has no equivalent cropping service — each granule matching the
current region (reprojected to WGS84 via `g.region -b`) and date range
is downloaded **whole**, as delivered by LP DAAC (only the reflectance
`_RFL_` NetCDF; the companion uncertainty and quality-mask files are
skipped, since *i.hyper.import*'s EMIT reader doesn't need them). Files
are cached locally and not re-fetched on a later run unless
`--overwrite` is given.

By default the module operates on the project/mapset it was launched
from, exactly like any other `r.in.*` importer. Give **project=** to
create (or reuse) a separate GRASS location instead, leaving the
calling session untouched.

### Output naming

`{output}_{acquisition timestamp}`, e.g. `dubai_20240619T081558` — the
full timestamp, not just the date, since a region can see more than one
EMIT overpass on the same day.

### Optional import (`-i`)

Runs [i.hyper.import](https://github.com/YannChemin/i.hyper.import)
(`product=emit`) on every downloaded granule, producing one raster_3d
cube per granule, with a real acquisition timestamp set via
`r3.timestamp`. `composites=`/`composites_custom=`/`strength=`/`-n` are
forwarded to *i.hyper.import*.

### Space-Time 3D Raster Dataset

**strds=** (needs **-i**) registers every cube imported in that run into
one **str3ds** (`t.create type=str3ds` + `t.register type=raster_3d`) —
the raster_3d equivalent of a STRDS, ready for `t.rast3d.list` and
temporal-3D algebra.

### Other flags

- **`-l`** — list matching granules (timestamp, cloud cover, filename)
  and exit, no download.
- **`-p`** — print the resolved WGS84 search bounding box and exit.

## Options

| Option | Description |
|---|---|
| `short_name` | NASA CMR collection short_name (default `EMITL2ARFL`) |
| `start`, `end` | Date range (`YYYY-MM-DD`) |
| `clouds` | Maximum granule cloud-cover percentage |
| `output` | Prefix for downloaded files / imported map names |
| `output_dir` | Local download cache (default `$HOME/RSDATA/EMIT_<output>`) |
| `token` | Earthdata Bearer token |
| `composites`, `composites_custom`, `strength` | Forwarded to `i.hyper.import` (needs `-i`) |
| `strds` | Name for a str3ds time series (needs `-i`) |
| `project`, `dbase`, `epsg` | Create/reuse a separate GRASS project instead of the current one |
| `-i` | Import via `i.hyper.import` |
| `-n` | Forwarded to `i.hyper.import -n` |
| `-l` | List granules and exit |
| `-p` | Print search bounding box and exit |

## Requirements

```
pip install netCDF4
```

Needed only for `-i` (i.hyper.import's EMIT reader); the download step
itself uses only the Python standard library.

A free [NASA Earthdata](https://urs.earthdata.nasa.gov) account and
Bearer token (*User Profile* → *Generate Token*).

## Install

```
g.extension extension=r.in.emit url=https://github.com/YannChemin/r.in.emit
```

## Testing

```
testsuite/test_r_in_emit.py
```

Queries NASA CMR for a small real EMIT granule over Plumergat (56400,
France) and downloads it to confirm the search → auth → download
pipeline works end-to-end; skipped automatically if no Earthdata token
is available, and needs live network access otherwise. A second test
covers `-i` import end-to-end when `netCDF4` is installed.

## License

Public domain — see [LICENSE](LICENSE) (Unlicense).

## References

- Green, R.O. et al. (2020). *The Earth Surface Mineral Dust Source
  Investigation (EMIT).* IEEE Aerospace Conference.
- [EMIT project site (JPL)](https://earth.jpl.nasa.gov/emit/)
- [NASA CMR API documentation](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html)
- [LP DAAC EMIT L2A RFL product page](https://lpdaac.usgs.gov/products/emitl2arflv001/)

## See also

- [r.in.sentinel](https://github.com/YannChemin/r.in.sentinel) — the
  Sentinel-2 equivalent this module's structure follows
- [i.hyper.import](https://github.com/YannChemin/i.hyper.import) — the
  importer this module optionally drives with `-i`
- [i.hyper.endmembers](https://github.com/YannChemin/i.hyper.endmembers),
  [i.hyper.speclookup](https://github.com/YannChemin/i.hyper.speclookup) —
  natural next steps once EMIT cubes are imported
