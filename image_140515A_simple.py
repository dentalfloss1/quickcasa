from __future__ import print_function

import argparse
import fnmatch
import glob
import math
import os
import re
from collections import OrderedDict


DEFAULT_MS_PATTERNS = ["*.ms", "obs*/*.ms"]
DEFAULT_OUTPUT_DIR = "images"
DEFAULT_NITER = 5000
DEFAULT_PIXELS_PER_SYNTH_BEAM = 10.0
DEFAULT_PB_FWHM = 1.0
DEFAULT_MIN_IMSIZE = 512
DEFAULT_MAX_IMSIZE = 8192
VLA_DISH_DIAMETER_M = 25.0
C_M_S = 299792458.0
ARCSEC_PER_RADIAN = 206264.806247

CASA_TOOLS = {}

VLA_BANDS = [
    {
        "name": "4",
        "patterns": ["EVLA_4#*", "VLA_4#*"],
        "min_hz": 54e6,
        "max_hz": 86e6,
    },
    {
        "name": "P",
        "patterns": ["EVLA_P#*", "VLA_P#*"],
        "min_hz": 224e6,
        "max_hz": 480e6,
    },
    {
        "name": "L",
        "patterns": ["EVLA_L#*", "VLA_L#*"],
        "min_hz": 1e9,
        "max_hz": 2e9,
    },
    {
        "name": "S",
        "patterns": ["EVLA_S#*", "VLA_S#*"],
        "min_hz": 2e9,
        "max_hz": 4e9,
    },
    {
        "name": "C",
        "patterns": ["EVLA_C#*", "VLA_C#*"],
        "min_hz": 4e9,
        "max_hz": 8e9,
    },
    {
        "name": "X",
        "patterns": ["EVLA_X#*", "VLA_X#*"],
        "min_hz": 8e9,
        "max_hz": 12e9,
    },
    {
        "name": "Ku",
        "patterns": ["EVLA_KU#*", "VLA_KU#*"],
        "min_hz": 12e9,
        "max_hz": 18e9,
    },
    {
        "name": "K",
        "patterns": ["EVLA_K#*", "VLA_K#*"],
        "min_hz": 18e9,
        "max_hz": 26.5e9,
    },
    {
        "name": "Ka",
        "patterns": ["EVLA_KA#*", "VLA_KA#*"],
        "min_hz": 26.5e9,
        "max_hz": 40e9,
    },
    {
        "name": "Q",
        "patterns": ["EVLA_Q#*", "VLA_Q#*"],
        "min_hz": 40e9,
        "max_hz": 50e9,
    },
]


def load_casa_tools():
    if CASA_TOOLS:
        return

    try:
        from casatasks import exportfits as casa_exportfits
        from casatasks import tclean as casa_tclean
        from casatools import msmetadata, table

        CASA_TOOLS["tclean"] = casa_tclean
        CASA_TOOLS["exportfits"] = casa_exportfits
        CASA_TOOLS["msmd"] = msmetadata()
        CASA_TOOLS["tb"] = table()
        return
    except ImportError:
        pass

    try:
        import taskinit

        CASA_TOOLS["msmd"] = taskinit.msmdtool()
        CASA_TOOLS["tb"] = taskinit.tbtool()
    except ImportError:
        raise RuntimeError(
            "CASA tools are not available. Run this script inside CASA, for example: "
            "casa -c image_140515A_simple.py calibrated.ms"
        )

    try:
        from tasks import exportfits as casa_exportfits
        from tasks import tclean as casa_tclean
    except ImportError:
        casa_tclean = globals().get("tclean")
        casa_exportfits = globals().get("exportfits")

    if casa_tclean is None or casa_exportfits is None:
        raise RuntimeError("Could not import CASA tasks tclean and exportfits")

    CASA_TOOLS["tclean"] = casa_tclean
    CASA_TOOLS["exportfits"] = casa_exportfits


def msmd_tool():
    return CASA_TOOLS["msmd"]


def table_tool():
    return CASA_TOOLS["tb"]


def split_csv(values):
    items = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                items.append(part)
    return items


def normalize_band_name(name):
    band_lookup = dict((band["name"].lower(), band["name"]) for band in VLA_BANDS)
    return band_lookup.get(name.lower())


def resolve_ms_list(patterns):
    ms_list = []
    seen = set()
    for pattern in patterns or DEFAULT_MS_PATTERNS:
        matches = sorted(glob.glob(pattern))
        if not matches and os.path.isdir(pattern):
            matches = [pattern]
        for match in matches:
            normalized = os.path.normpath(match)
            if not normalized.endswith(".ms"):
                continue
            if normalized not in seen:
                ms_list.append(normalized)
                seen.add(normalized)
    return ms_list


def field_entries(vis):
    msmd = msmd_tool()
    msmd.open(vis)
    try:
        names = list(msmd.fieldnames())
    finally:
        msmd.close()
    return [{"id": field_id, "name": name} for field_id, name in enumerate(names)]


def field_ids_for_intent(vis, intent_selector):
    if intent_selector.lower() in ["*", "all"]:
        return [entry["id"] for entry in field_entries(vis)]

    msmd = msmd_tool()
    selected = set()
    msmd.open(vis)
    try:
        intents = list(msmd.intents())
        for intent in intents:
            if intent_selector.upper() not in intent.upper():
                continue
            for field_id in list(msmd.fieldsforintent(intent)):
                selected.add(int(field_id))
    finally:
        msmd.close()
    return sorted(selected)


def match_field_selectors(vis, selectors):
    fields = field_entries(vis)
    selected = OrderedDict()

    for selector in selectors:
        if selector.isdigit():
            selector_id = int(selector)
            for field in fields:
                if field["id"] == selector_id:
                    selected[field["id"]] = field
                    break
            else:
                raise RuntimeError("Field id {0} not found in {1}".format(selector, vis))
            continue

        matches = [
            field
            for field in fields
            if fnmatch.fnmatch(field["name"].lower(), selector.lower())
            or field["name"].lower() == selector.lower()
        ]
        if not matches:
            raise RuntimeError("Field selector {0} did not match {1}".format(selector, vis))
        for field in matches:
            selected[field["id"]] = field

    return list(selected.values())


def selected_fields(vis, args):
    fields = field_entries(vis)
    fields_by_id = dict((field["id"], field) for field in fields)
    exclude_selectors = split_csv(args.exclude_field)

    if args.all_fields:
        selected = fields
    elif args.field:
        selected = match_field_selectors(vis, split_csv(args.field))
    else:
        target_ids = field_ids_for_intent(vis, args.intent)
        if target_ids:
            selected = [fields_by_id[field_id] for field_id in target_ids]
        else:
            print(
                "No fields with intent containing {0} found in {1}; imaging all fields".format(
                    args.intent, vis
                )
            )
            selected = fields

    if exclude_selectors:
        excluded = set(field["id"] for field in match_field_selectors(vis, exclude_selectors))
        selected = [field for field in selected if field["id"] not in excluded]

    return selected


def spw_names(vis):
    tb = table_tool()
    tb.open(os.path.join(vis, "SPECTRAL_WINDOW"))
    try:
        return list(tb.getcol("NAME"))
    finally:
        tb.close()


def mean_frequency_hz_for_spw_id(vis, spw_id):
    msmd = msmd_tool()
    msmd.open(vis)
    try:
        return float(msmd.meanfreq(spw_id))
    finally:
        msmd.close()


def mean_frequency_hz_for_spw_ids(vis, spw_ids):
    freqs = [mean_frequency_hz_for_spw_id(vis, spw_id) for spw_id in spw_ids]
    if not freqs:
        raise RuntimeError("No SPWs selected in {0}".format(vis))
    return sum(freqs) / float(len(freqs))


def band_from_spw_name(spw_name):
    upper_name = spw_name.upper()
    for band in VLA_BANDS:
        for pattern in band["patterns"]:
            if fnmatch.fnmatch(upper_name, pattern):
                return band["name"]
    return None


def band_from_frequency(freq_hz):
    for band in VLA_BANDS:
        if band["min_hz"] <= freq_hz < band["max_hz"]:
            return band["name"]
    return None


def vla_band_for_spw(vis, spw_id, spw_name):
    return band_from_spw_name(spw_name) or band_from_frequency(
        mean_frequency_hz_for_spw_id(vis, spw_id)
    )


def band_spws_in_ms(vis, requested_bands):
    names = spw_names(vis)
    requested = None
    if requested_bands:
        requested = set()
        for band in requested_bands:
            normalized = normalize_band_name(band)
            if normalized is None:
                raise RuntimeError(
                    "Unknown VLA band {0}. Choose one of: {1}".format(
                        band, ", ".join(band_info["name"] for band_info in VLA_BANDS)
                    )
                )
            requested.add(normalized)

    grouped = OrderedDict((band["name"], []) for band in VLA_BANDS)
    unmatched = []
    for spw_id, name in enumerate(names):
        band = vla_band_for_spw(vis, spw_id, name)
        if band is None:
            unmatched.append(spw_id)
            continue
        if requested is None or band in requested:
            grouped[band].append(spw_id)

    found = [(band, spw_ids) for band, spw_ids in grouped.items() if spw_ids]
    if unmatched:
        print(
            "Ignoring SPWs with frequencies outside the VLA band table in {0}: {1}".format(
                vis, spw_selection(unmatched)
            )
        )
    return found


def max_baseline_m(vis):
    tb = table_tool()
    tb.open(os.path.join(vis, "ANTENNA"))
    try:
        positions = tb.getcol("POSITION")
    finally:
        tb.close()

    nant = positions.shape[1]
    max_bl = 0.0
    for i in range(nant):
        xi, yi, zi = positions[:, i]
        for j in range(i + 1, nant):
            xj, yj, zj = positions[:, j]
            baseline = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2)
            max_bl = max(max_bl, baseline)

    if max_bl <= 0.0:
        raise RuntimeError("Could not compute a valid max baseline for {0}".format(vis))
    return max_bl


def spw_selection(spw_ids):
    return ",".join(str(spw_id) for spw_id in spw_ids)


def parse_spw_ids_from_selection(spw, nspw):
    if spw is None or spw.strip() in ["", "*"]:
        return list(range(nspw))

    selected = []
    for part in spw.split(","):
        base = part.split(":", 1)[0].strip()
        if base in ["", "*"]:
            selected.extend(range(nspw))
        elif "~" in base:
            start, stop = base.split("~", 1)
            selected.extend(range(int(start), int(stop) + 1))
        else:
            selected.append(int(base))

    valid = []
    for spw_id in selected:
        if spw_id < 0 or spw_id >= nspw:
            raise RuntimeError("SPW id {0} is outside the available range 0-{1}".format(spw_id, nspw - 1))
        if spw_id not in valid:
            valid.append(spw_id)
    return valid


def selected_spw_groups(vis, args):
    if args.spw:
        spw_ids = parse_spw_ids_from_selection(args.spw, len(spw_names(vis)))
        return [(args.band_label, spw_ids, args.spw)]

    bands = band_spws_in_ms(vis, split_csv(args.band))
    return [(band, spw_ids, spw_selection(spw_ids)) for band, spw_ids in bands]


def cell_arcsec_from_ms_and_spw_ids(vis, spw_ids, pixels_per_synth_beam):
    freq_hz = mean_frequency_hz_for_spw_ids(vis, spw_ids)
    wavelength_m = C_M_S / freq_hz
    beam_rad = wavelength_m / max_baseline_m(vis)
    return beam_rad * ARCSEC_PER_RADIAN / pixels_per_synth_beam


def cell_string(cell_arcsec):
    return "{0:.6f}arcsec".format(cell_arcsec)


def primary_beam_fwhm_arcsec(vis, spw_ids):
    freq_hz = mean_frequency_hz_for_spw_ids(vis, spw_ids)
    wavelength_m = C_M_S / freq_hz
    return 1.02 * wavelength_m / VLA_DISH_DIAMETER_M * ARCSEC_PER_RADIAN


def is_good_imsize(value):
    if value < 1:
        return False
    remainder = value
    for factor in [2, 3, 5, 7]:
        while remainder % factor == 0:
            remainder = remainder // factor
    return remainder == 1


def next_good_imsize(value):
    candidate = max(1, int(math.ceil(value)))
    if candidate % 2:
        candidate += 1
    while not is_good_imsize(candidate):
        candidate += 2
    return candidate


def auto_imsize(vis, spw_ids, cell_arcsec, args):
    pb_arcsec = primary_beam_fwhm_arcsec(vis, spw_ids)
    raw_imsize = pb_arcsec * args.pb_fwhm / cell_arcsec
    bounded = max(args.min_imsize, min(args.max_imsize, raw_imsize))
    return next_good_imsize(bounded)


def imsize_for_group(vis, spw_ids, cell_arcsec, args):
    if args.imsize.lower() == "auto":
        return auto_imsize(vis, spw_ids, cell_arcsec, args)

    imsize = int(args.imsize)
    if imsize <= 0:
        raise RuntimeError("--imsize must be a positive integer or auto")
    return imsize


def safe_name(value):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    safe = safe.strip("._")
    return safe or "unnamed"


def ms_stem(vis):
    relpath = os.path.relpath(vis, os.getcwd())
    if relpath.endswith(".ms"):
        relpath = relpath[:-3]
    return safe_name(relpath.replace(os.sep, "__"))


def image_name_for_ms(vis, field, band, output_dir):
    return os.path.join(
        output_dir,
        "{0}_{1}_{2}".format(ms_stem(vis), safe_name(field["name"]), safe_name(band)),
    )


def image_products(imagename, deconvolver):
    products = [imagename + ".image"]
    if deconvolver == "mtmfs":
        products.insert(0, imagename + ".image.tt0")
    return products


def output_image_for_export(imagename, deconvolver):
    for image in image_products(imagename, deconvolver):
        if os.path.exists(image):
            return image
    return image_products(imagename, deconvolver)[0]


def image_exists(imagename, fitsname, deconvolver):
    if os.path.exists(fitsname):
        return True
    return any(os.path.exists(product) for product in image_products(imagename, deconvolver))


def is_zero_row_selection_error(exc):
    return "Data selection ended with 0 rows" in str(exc)


def data_column_for_ms(vis, requested):
    if requested != "auto":
        return requested

    tb = table_tool()
    tb.open(vis)
    try:
        columns = list(tb.colnames())
    finally:
        tb.close()

    if "CORRECTED_DATA" in columns:
        return "corrected"
    return "data"


def make_tclean_kwargs(vis, field, spw, imsize, cell, imagename, data_column, args):
    kwargs = {
        "vis": vis,
        "field": str(field["id"]),
        "spw": spw,
        "pblimit": args.pblimit,
        "imsize": imsize,
        "cell": cell,
        "gridder": args.gridder,
        "specmode": args.specmode,
        "deconvolver": args.deconvolver,
        "weighting": args.weighting,
        "niter": args.niter,
        "datacolumn": data_column,
        "imagename": imagename,
        "interactive": args.interactive,
    }

    if args.robust is not None:
        kwargs["robust"] = args.robust
    if args.deconvolver == "mtmfs":
        kwargs["nterms"] = args.nterms
    if args.threshold:
        kwargs["threshold"] = args.threshold

    return kwargs


def print_imaging_summary(vis, field, band, spw, imsize, cell, data_column, imagename):
    print("")
    print("Imaging {0}".format(vis))
    print("  field    = {0} (id {1})".format(field["name"], field["id"]))
    print("  band     = {0}".format(band))
    print("  spw      = {0}".format(spw))
    print("  datacol  = {0}".format(data_column))
    print("  imsize   = {0}".format(imsize))
    print("  cell     = {0}".format(cell))
    print("  imagename= {0}".format(imagename))


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Continuum-image calibrated VLA measurement sets. By default the script "
            "discovers fields with TARGET intent, groups SPWs by VLA band, derives a "
            "cell size from the longest baseline, and exports FITS images."
        )
    )
    parser.add_argument(
        "vis",
        nargs="*",
        help=(
            "Measurement set paths or shell globs. Defaults to: {0}".format(
                ", ".join(DEFAULT_MS_PATTERNS)
            )
        ),
    )
    parser.add_argument("--field", action="append", help="Field name/id/glob to image. May be repeated or comma-separated.")
    parser.add_argument("--exclude-field", action="append", help="Field name/id/glob to skip. May be repeated or comma-separated.")
    parser.add_argument("--all-fields", action="store_true", help="Image every field instead of only fields with TARGET intent.")
    parser.add_argument("--intent", default="TARGET", help="Intent substring used for automatic field discovery. Default: TARGET.")
    parser.add_argument("--band", action="append", help="VLA band to image. May be repeated or comma-separated.")
    parser.add_argument("--spw", help="Explicit CASA SPW selection. If set, automatic band grouping is disabled.")
    parser.add_argument("--band-label", default="spw", help="Image-name label used with --spw. Default: spw.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for CASA image products and FITS files.")
    parser.add_argument("--imsize", default="auto", help="Image size in pixels, or auto. Default: auto.")
    parser.add_argument("--min-imsize", type=int, default=DEFAULT_MIN_IMSIZE, help="Minimum auto image size. Default: 512.")
    parser.add_argument("--max-imsize", type=int, default=DEFAULT_MAX_IMSIZE, help="Maximum auto image size. Default: 8192.")
    parser.add_argument("--pb-fwhm", type=float, default=DEFAULT_PB_FWHM, help="Primary-beam FWHM count used for auto imsize. Default: 1.0.")
    parser.add_argument("--pixels-per-beam", type=float, default=DEFAULT_PIXELS_PER_SYNTH_BEAM, help="Pixels across the synthesized beam for auto cell size. Default: 10.")
    parser.add_argument("--niter", type=int, default=DEFAULT_NITER, help="tclean niter. Default: 5000.")
    parser.add_argument("--threshold", help="Optional tclean threshold, e.g. 30uJy.")
    parser.add_argument("--specmode", default="mfs", help="tclean specmode. Default: mfs.")
    parser.add_argument("--deconvolver", default="hogbom", choices=["hogbom", "clark", "multiscale", "mtmfs"], help="tclean deconvolver. Default: hogbom.")
    parser.add_argument("--nterms", type=int, default=2, help="tclean nterms when --deconvolver mtmfs is used. Default: 2.")
    parser.add_argument("--gridder", default="standard", help="tclean gridder. Default: standard.")
    parser.add_argument("--weighting", default="natural", help="tclean weighting. Default: natural.")
    parser.add_argument("--robust", type=float, help="Optional tclean robust value for Briggs weighting.")
    parser.add_argument("--pblimit", type=float, default=-1e-12, help="tclean pblimit. Default: -1e-12.")
    parser.add_argument("--datacolumn", default="auto", choices=["auto", "corrected", "data"], help="tclean datacolumn. Default: auto.")
    parser.add_argument("--interactive", action="store_true", help="Run tclean interactively.")
    parser.add_argument("--overwrite", action="store_true", help="Re-run tclean even when image products already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned imaging jobs without running tclean.")
    return parser.parse_args()


def main():
    args = parse_args()
    load_casa_tools()

    ms_list = resolve_ms_list(args.vis)
    if not ms_list:
        raise RuntimeError(
            "No measurement sets found. Provide paths/globs or place calibrated .ms "
            "datasets under one of: {0}".format(", ".join(DEFAULT_MS_PATTERNS))
        )

    if not os.path.isdir(args.output_dir):
        os.makedirs(args.output_dir)

    for vis in ms_list:
        fields = selected_fields(vis, args)
        spw_groups = selected_spw_groups(vis, args)
        if not fields:
            print("Skipping {0}: no selected fields".format(vis))
            continue
        if not spw_groups:
            print("Skipping {0}: no selected VLA SPWs".format(vis))
            continue

        data_column = data_column_for_ms(vis, args.datacolumn)

        for field in fields:
            for band, spw_ids, spw in spw_groups:
                cell_arcsec = cell_arcsec_from_ms_and_spw_ids(
                    vis, spw_ids, args.pixels_per_beam
                )
                cell = cell_string(cell_arcsec)
                imsize = imsize_for_group(vis, spw_ids, cell_arcsec, args)
                imagename = image_name_for_ms(vis, field, band, args.output_dir)
                fitsname = imagename + ".fits"

                if image_exists(imagename, fitsname, args.deconvolver) and not args.overwrite:
                    print("")
                    print("Skipping existing image:")
                    print("  imagename= {0}".format(imagename))
                    print("  fitsname = {0}".format(fitsname))
                    continue

                print_imaging_summary(
                    vis, field, band, spw, imsize, cell, data_column, imagename
                )

                if args.dry_run:
                    continue

                try:
                    CASA_TOOLS["tclean"](
                        **make_tclean_kwargs(
                            vis,
                            field,
                            spw,
                            imsize,
                            cell,
                            imagename,
                            data_column,
                            args,
                        )
                    )
                except RuntimeError as exc:
                    if is_zero_row_selection_error(exc):
                        print(
                            "Skipping {0} field {1} band {2}: selected 0 rows".format(
                                vis, field["name"], band
                            )
                        )
                        continue
                    raise

                CASA_TOOLS["exportfits"](
                    imagename=output_image_for_export(imagename, args.deconvolver),
                    fitsimage=fitsname,
                    overwrite=True,
                )


if __name__ == "__main__":
    main()
