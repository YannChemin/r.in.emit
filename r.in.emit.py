#!/usr/bin/env python3
# %Module
# % description: Downloads NASA EMIT L2A Surface Reflectance granules via NASA CMR/LP DAAC and optionally imports them as raster_3d hyperspectral cubes, into the current GRASS project or a new one.
# % keyword: imagery
# % keyword: hyperspectral
# % keyword: EMIT
# % keyword: download
# % keyword: NASA
# % keyword: CMR
# % keyword: LP DAAC
# % keyword: metadata
# %end

# %option
# % key: short_name
# % type: string
# % required: no
# % multiple: no
# % answer: EMITL2ARFL
# % description: NASA CMR collection short_name to search (EMIT L2A Estimated Surface Reflectance)
# % guisection: Config
# %end

# %option
# % key: start
# % type: string
# % required: yes
# % multiple: no
# % description: Start date (YYYY-MM-DD)
# % guisection: Filter
# %end

# %option
# % key: end
# % type: string
# % required: yes
# % multiple: no
# % description: End date (YYYY-MM-DD)
# % guisection: Filter
# %end

# %option
# % key: clouds
# % type: integer
# % required: no
# % multiple: no
# % description: Maximum granule cloud-cover percentage [0, 100]
# % guisection: Filter
# %end

# %option
# % key: output
# % type: string
# % required: no
# % multiple: no
# % answer: emit
# % description: Prefix for downloaded file naming and imported raster_3d map names
# % guisection: Output
# %end

# %option
# % key: output_dir
# % type: string
# % required: no
# % multiple: no
# % description: Local directory to save downloaded EMIT granules (default: $HOME/RSDATA/EMIT_<output>)
# % guisection: Output
# %end

# %option
# % key: token
# % type: string
# % required: no
# % multiple: no
# % description: NASA Earthdata Bearer token (default: EARTHDATA_TOKEN env var, or a TOKEN file in output_dir)
# % guisection: Config
# %end

# %flag
# % key: l
# % description: List matching granules and exit without downloading
# %end

# %flag
# % key: p
# % description: Print the resolved search bounding box and exit
# %end

# %flag
# % key: i
# % description: Import downloaded granules with i.hyper.import as raster_3d hyperspectral cubes
# %end

# %option
# % key: composites
# % type: string
# % required: no
# % multiple: yes
# % options: rgb,cir,swir_agriculture,swir_geology
# % description: Composites to generate during import (forwarded to i.hyper.import; only used with -i)
# % guisection: Import
# %end

# %option
# % key: composites_custom
# % type: string
# % required: no
# % description: Wavelengths for a custom composite, e.g. 850,1650,660 (forwarded to i.hyper.import; only used with -i)
# % guisection: Import
# %end

# %option
# % key: strength
# % type: integer
# % required: no
# % answer: 96
# % description: Cropping intensity for composites - upper brightness level (forwarded to i.hyper.import; only used with -i)
# % guisection: Import
# %end

# %flag
# % key: n
# % description: Record full source-band validity in bands.validity instead of nulling bad bands (forwarded to i.hyper.import; only used with -i)
# % guisection: Import
# %end

# %option
# % key: strds
# % type: string
# % required: no
# % multiple: no
# % description: Name for a Space-Time 3D Raster Dataset (str3ds) collecting all imported cubes over time (requires -i)
# % guisection: Import
# %end

# %option
# % key: project
# % type: string
# % required: no
# % multiple: no
# % description: Name of a new GRASS project/location to create for the downloaded/imported data (default: use the project/mapset this module was launched from)
# % guisection: Project
# %end

# %option
# % key: dbase
# % type: string
# % required: no
# % multiple: no
# % description: GRASS database directory in which to create a new project (default: the current GISDBASE); only used with project=
# % guisection: Project
# %end

# %option
# % key: epsg
# % type: integer
# % required: no
# % answer: 4326
# % description: EPSG code for a new project's CRS (EMIT L2A reflectance is delivered orthorectified on a WGS84 geographic grid); only used with project=
# % guisection: Project
# %end

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import grass.script as gs

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
LPDAAC_HOST = "lpdaac.earthdatacloud.nasa.gov"

# ---------------------------------------------------------------------------
# Region / search bounding box (always read from the *calling* session's own
# current region, regardless of whether output goes to that same project or
# a brand new one -- mirrors r.in.sentinel's convention of always trusting
# the caller's g.region as the area of interest).
# ---------------------------------------------------------------------------


def get_region_bbox_latlon() -> tuple[float, float, float, float]:
    """Return (west, south, east, north) of the current region in WGS84.

    g.region -b always reports ll_n/ll_s/ll_w/ll_e (reprojected WGS84
    corners) regardless of whether the current project is itself
    geographic or projected, so no separate branching is needed the way
    r.in.sentinel's centre-based helper requires.
    """
    region = gs.parse_command("g.region", flags="pb", format="shell")
    return (
        float(region["ll_w"]),
        float(region["ll_s"]),
        float(region["ll_e"]),
        float(region["ll_n"]),
    )

# ---------------------------------------------------------------------------
# NASA CMR search
# ---------------------------------------------------------------------------


def fetch_granules(short_name, bbox, start, end, clouds=None, page_size=100):
    """Query NASA CMR for granules of short_name intersecting bbox/date range.

    Parameters
    ----------
    short_name : str
    bbox : tuple of (west, south, east, north)
    start, end : str (YYYY-MM-DD)
    clouds : int or None
        Maximum cloud-cover percentage filter (applied client-side: CMR's
        granule.json response includes a top-level 'cloud_cover' field but
        the search API itself has no cloud-cover query parameter for this
        collection).

    Returns
    -------
    list of dict
        Raw CMR granule entries.
    """
    west, south, east, north = bbox
    bbox_str = f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}"
    base_params = (
        f"short_name={short_name}"
        f"&bounding_box={bbox_str}"
        f"&temporal={start}T00:00:00Z,{end}T23:59:59Z"
        f"&page_size={page_size}"
        f"&sort_key=start_date"
    )

    granules = []
    for page in range(1, 50):
        url = f"{CMR_URL}?{base_params}&page_num={page}"
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = json.load(r)
        except Exception as e:
            gs.fatal(f"NASA CMR search failed: {e}")
        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            break
        granules.extend(entries)
        gs.verbose(f"CMR page {page}: {len(entries)} granule(s)")
        if len(entries) < page_size:
            break
        time.sleep(0.2)

    if clouds is not None:
        before = len(granules)
        granules = [g for g in granules if int(g.get("cloud_cover", 0) or 0) <= clouds]
        gs.verbose(f"Cloud filter (<= {clouds}%): {before} -> {len(granules)} granule(s)")

    return granules


def granule_datetime(entry) -> datetime:
    """Parse a CMR granule entry's acquisition start time."""
    ts = entry["time_start"].replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def granule_rfl_url(entry) -> str | None:
    """Return the direct-access HTTPS URL of the granule's reflectance (RFL)
    NetCDF file, skipping the companion uncertainty (RFLUNCERT) and mask
    (MASK) files that i.hyper.import's EMIT reader does not use."""
    for link in entry.get("links", []):
        href = link.get("href", "")
        rel = link.get("rel", "")
        if "data#" not in rel:
            continue
        if LPDAAC_HOST not in href:
            continue
        if not href.endswith(".nc"):
            continue
        fname = href.split("/")[-1]
        if "_RFLUNCERT_" in fname or "_MASK_" in fname:
            continue
        return href
    return None

# ---------------------------------------------------------------------------
# Earthdata authentication + download
# ---------------------------------------------------------------------------


def load_token(token_opt, output_dir) -> str:
    token = (token_opt or "").strip()
    if not token:
        token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if not token:
        token_file = Path(output_dir) / "TOKEN"
        if token_file.exists():
            token = token_file.read_text().strip()
    if not token:
        gs.fatal(
            "No NASA Earthdata token found. Provide token=, set the "
            "EARTHDATA_TOKEN environment variable, or write it to "
            f"{Path(output_dir) / 'TOKEN'}. Generate one at "
            "https://urs.earthdata.nasa.gov (User Profile -> Generate Token)."
        )
    return token


def setup_auth(token):
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(),
        urllib.request.HTTPRedirectHandler(),
    )
    opener.addheaders = [
        ("User-Agent", "r.in.emit/1.0"),
        ("Authorization", f"Bearer {token}"),
    ]
    urllib.request.install_opener(opener)


def download_file(url, dest: Path) -> bool:
    """Download url to dest unless dest already exists and is non-empty
    (skip, not re-download) -- EMIT granules are large (hundreds of MB to a
    few GB), so a persistent, resumable-by-skip local cache is the sane
    default; use --overwrite to force a re-download."""
    if dest.exists() and dest.stat().st_size > 0 and not gs.overwrite():
        gs.verbose(f"  [skip] {dest.name} (already downloaded)")
        return True

    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        gs.message(f"  [fetch] {dest.name} …")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)
        size_mb = dest.stat().st_size / 1e6
        gs.verbose(f"  [fetch] {dest.name}: {size_mb:.1f} MB")
        return True
    except urllib.error.HTTPError as e:
        gs.warning(f"  [fail] {dest.name}: HTTP {e.code}")
    except Exception as e:
        gs.warning(f"  [fail] {dest.name}: {e}")
    if tmp.exists():
        tmp.unlink()
    return False

# ---------------------------------------------------------------------------
# Target project/mapset (default: the project this module was launched
# from; optionally a brand new one)
# ---------------------------------------------------------------------------


def resolve_target_environment(project, dbase, epsg):
    """Returns (env, gisrc_to_clean_up).

    env=None means "use the calling process's own GRASS session, as-is"
    (the default operation the task calls for). When project= is given, a
    new location is created (grass.script.create_project) and a separate
    environment pointing at its PERMANENT mapset is returned instead, so
    every subsequent gs.run_command(..., env=env) call in this script
    targets the new project without disturbing the caller's own session.
    """
    if not project:
        return None, None

    genv = gs.gisenv()
    dbase = dbase or genv["GISDBASE"]
    project_path = Path(dbase) / project

    if project_path.exists():
        gs.message(f"Project '{project}' already exists at {project_path} — using it.")
    else:
        gs.message(f"Creating new project '{project}' (EPSG:{epsg}) at {dbase}…")
        gs.create_project(path=dbase, name=project, epsg=epsg)

    gisrc, env = gs.create_environment(dbase, project, "PERMANENT")
    return env, gisrc

# ---------------------------------------------------------------------------
# Import via i.hyper.import + timestamp + STR3DS
# ---------------------------------------------------------------------------


def import_granule(nc_path, map_name, options, flags, env):
    """Import one downloaded EMIT RFL granule as a raster_3d cube via
    i.hyper.import, in the target environment (current project or the new
    one resolved by resolve_target_environment)."""
    existing = gs.list_grouped("raster_3d", env=env).get(
        gs.gisenv(env=env)["MAPSET"], []
    )
    if map_name in existing and not gs.overwrite():
        gs.message(f"  [skip] {map_name} already imported (use --overwrite to redo).")
        return False

    kwargs = dict(
        input=str(nc_path),
        product="emit",
        output=map_name,
        strength=options.get("strength", "96") or "96",
        quiet=True,
    )
    if options.get("composites"):
        kwargs["composites"] = options["composites"]
    if options.get("composites_custom"):
        kwargs["composites_custom"] = options["composites_custom"]
    import_flags = "n" if flags.get("n") else ""

    gs.message(f"  Importing {map_name} via i.hyper.import…")
    try:
        gs.run_command("i.hyper.import", flags=import_flags, env=env, **kwargs)
        return True
    except Exception as e:
        gs.warning(f"  i.hyper.import failed for {map_name}: {e}")
        return False


def set_timestamp(map_name, acq_time: datetime, env):
    timestamp_str = acq_time.strftime("%d %b %Y %H:%M:%S.%f")[:-3]
    gs.run_command("r3.timestamp", map=map_name, date=timestamp_str, quiet=True, env=env)


def create_str3ds(strds_name, map_list, short_name, start, end, env):
    """t.create/t.register are invoked as separate module subprocesses
    (via env=, targeting the current or a newly-created project), each of
    which initialises its own temporal DB connection -- unlike
    grass.script.run_command, grass.temporal.init() has no env= parameter
    and is bound to this calling process's own ambient GRASS session, so
    it cannot be used here to target a different one and is not needed:
    t.create/t.register do not depend on this process having called it."""
    gs.message(f"Creating Space-Time 3D Raster Dataset '{strds_name}'…")

    gs.run_command(
        "t.create",
        type="str3ds",
        temporaltype="absolute",
        output=strds_name,
        title=f"EMIT {short_name}",
        description=(
            f"Imported by r.in.emit from NASA CMR ({short_name}), "
            f"{start} to {end}"
        ),
        overwrite=True,
        quiet=True,
        env=env,
    )
    gs.run_command(
        "t.register",
        type="raster_3d",
        input=strds_name,
        maps=",".join(map_list),
        overwrite=True,
        quiet=True,
        env=env,
    )
    gs.message(f"STR3DS '{strds_name}': {len(map_list)} cube(s) registered.")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    short_name = options["short_name"]
    start = options["start"]
    end = options["end"]
    clouds_raw = options["clouds"]
    clouds = int(clouds_raw) if clouds_raw else None
    output_prefix = options["output"]
    output_dir_opt = options.get("output_dir")
    token_opt = options.get("token")

    list_only = flags["l"]
    print_bbox = flags["p"]
    do_import = flags["i"]
    strds_name = options.get("strds") or None
    if strds_name and not do_import:
        gs.fatal("strds= requires -i (imported raster_3d cubes are what get registered).")

    project = options.get("project") or None
    dbase = options.get("dbase") or None
    epsg = int(options.get("epsg") or "4326")

    output_dir = Path(output_dir_opt) if output_dir_opt else (
        Path.home() / "RSDATA" / f"EMIT_{output_prefix}"
    )

    # --- Search bounding box, always from the calling session's own region
    gs.message("Determining search bounding box from the current region…")
    bbox = get_region_bbox_latlon()
    west, south, east, north = bbox
    gs.message(
        f"Bounding box (WGS84): w={west:.4f} s={south:.4f} e={east:.4f} n={north:.4f}"
    )

    if print_bbox:
        gs.message(
            f"west={west} south={south} east={east} north={north} "
            f"short_name={short_name} start={start} end={end}"
        )
        return 0

    # --- Search CMR --------------------------------------------------------
    gs.message(f"Querying NASA CMR for {short_name} granules ({start} to {end})…")
    granules = fetch_granules(short_name, bbox, start, end, clouds)
    gs.message(f"Found {len(granules)} granule(s).")
    if not granules:
        return 0

    targets = []  # (map_name, url, acq_time)
    for g in granules:
        url = granule_rfl_url(g)
        if not url:
            gs.verbose(f"  Skipping {g.get('title', '?')}: no RFL .nc data link found.")
            continue
        acq_time = granule_datetime(g)
        map_name = f"{output_prefix}_{acq_time.strftime('%Y%m%dT%H%M%S')}"
        targets.append((map_name, url, acq_time, g))

    if list_only:
        gs.message("Available granules:")
        for map_name, url, acq_time, g in targets:
            cc = g.get("cloud_cover", "n/a")
            print(f"{acq_time.isoformat()}  cloud_cover={cc}%  {url.split('/')[-1]}")
        return 0

    # --- Download ------------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    token = load_token(token_opt, output_dir)
    setup_auth(token)

    gs.message(f"Downloading to {output_dir} …")
    downloaded = []  # (map_name, nc_path, acq_time)
    for map_name, url, acq_time, g in targets:
        year_dir = output_dir / str(acq_time.year)
        year_dir.mkdir(exist_ok=True)
        dest = year_dir / url.split("/")[-1]
        if download_file(url, dest):
            downloaded.append((map_name, dest, acq_time))

    gs.message(f"Downloaded/available: {len(downloaded)} of {len(targets)} granule(s).")

    # --- Target project/mapset for import ----------------------------------
    env, gisrc = resolve_target_environment(project, dbase, epsg)
    try:
        if not do_import:
            gs.message(
                "Done (download only). Use -i to also import via i.hyper.import."
            )
            return 0

        gs.message("Importing granules via i.hyper.import…")
        imported = []  # (map_name, acq_time)
        for map_name, nc_path, acq_time in downloaded:
            ok = import_granule(nc_path, map_name, options, flags, env)
            if ok:
                set_timestamp(map_name, acq_time, env)
                imported.append((map_name, acq_time))

        gs.message(f"Imported {len(imported)} of {len(downloaded)} cube(s).")

        if imported:
            # Set a sensible default region from the first imported cube --
            # matters most when project= created a brand new, empty location.
            gs.run_command(
                "g.region", raster_3d=imported[0][0], flags="ps", quiet=True, env=env
            )

        if strds_name and imported:
            create_str3ds(
                strds_name, [m for m, _ in imported], short_name, start, end, env
            )
        elif strds_name:
            gs.warning("No cubes imported; STR3DS not created.")

        return 0
    finally:
        if gisrc and os.path.exists(gisrc):
            os.remove(gisrc)


if __name__ == "__main__":
    options, flags = gs.parser()
    sys.exit(main())
