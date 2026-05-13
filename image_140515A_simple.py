import glob
import fnmatch
import math
import os

try:
    from casatasks import tclean, exportfits
    from casatools import msmetadata, table
except ImportError:
    from taskinit import *
    msmd = msmdtool()
    tb = tbtool()
else:
    msmd = msmetadata()
    tb = table()


TARGET = "140515A"
MS_GLOB = "obs*/14A*.ms"

IMSIZE = 5120
NITER = 5000
PIXELS_PER_SYNTH_BEAM = 10.0

VLA_BAND_SPWS = [
    ("P", "EVLA_P#*"),
    ("L", "EVLA_L#*"),
    ("S", "EVLA_S#*"),
    ("C", "EVLA_C#*"),
    ("X", "EVLA_X#*"),
    ("Ku", "EVLA_KU#*"),
    ("K", "EVLA_K#*"),
    ("Ka", "EVLA_KA#*"),
    ("Q", "EVLA_Q#*"),
]


def field_exists(vis, field_name):
    msmd.open(vis)
    try:
        return field_name in list(msmd.fieldnames())
    finally:
        msmd.close()


def spw_names(vis):
    tb.open(os.path.join(vis, "SPECTRAL_WINDOW"))
    try:
        return list(tb.getcol("NAME"))
    finally:
        tb.close()


def band_spws_in_ms(vis):
    names = spw_names(vis)
    found = []
    for band, spw_selector in VLA_BAND_SPWS:
        spw_ids = [
            spw_id
            for spw_id, name in enumerate(names)
            if fnmatch.fnmatch(name.upper(), spw_selector)
        ]
        if spw_ids:
            found.append((band, spw_ids))
    return found


def max_baseline_m(vis):
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


def mean_frequency_hz_for_spw_ids(vis, spw_ids):
    msmd.open(vis)
    try:
        freqs = [msmd.meanfreq(spw_id) for spw_id in spw_ids]
    finally:
        msmd.close()

    if not freqs:
        raise RuntimeError(
            "No SPWs matched selector {0} in {1}".format(spw_selection(spw_ids), vis)
        )
    return sum(freqs) / float(len(freqs))


def cell_from_ms_and_spw_ids(vis, spw_ids):
    c_m_s = 299792458.0
    freq_hz = mean_frequency_hz_for_spw_ids(vis, spw_ids)
    wavelength_m = c_m_s / freq_hz
    beam_rad = wavelength_m / max_baseline_m(vis)
    cell_arcsec = beam_rad * 206264.806247 / PIXELS_PER_SYNTH_BEAM
    return "{0:.6f}arcsec".format(cell_arcsec)


def image_name_for_ms(vis, band):
    base = os.path.basename(vis)
    if base.endswith(".ms"):
        base = base[:-3]
    return os.path.join("images", base + "_" + TARGET + "_" + band)


def image_exists(imagename, fitsname):
    return os.path.exists(imagename + ".image") or os.path.exists(fitsname)


def is_zero_row_selection_error(exc):
    return "Data selection ended with 0 rows" in str(exc)


def main():
    ms_list = sorted(glob.glob(MS_GLOB))
    if not ms_list:
        raise RuntimeError("No measurement sets found matching {0}".format(MS_GLOB))

    if not os.path.isdir("images"):
        os.makedirs("images")

    for vis in ms_list:
        if not field_exists(vis, TARGET):
            print("Skipping {0}: target {1} not found".format(vis, TARGET))
            continue

        for band, spw_ids in band_spws_in_ms(vis):
            spw = spw_selection(spw_ids)
            cell = cell_from_ms_and_spw_ids(vis, spw_ids)
            imagename = image_name_for_ms(vis, band)
            fitsname = imagename + ".fits"

            if image_exists(imagename, fitsname):
                print("")
                print("Skipping existing image:")
                print("  imagename= {0}".format(imagename))
                print("  fitsname = {0}".format(fitsname))
                continue

            print("")
            print("Imaging {0}".format(vis))
            print("  field    = {0}".format(TARGET))
            print("  band     = {0}".format(band))
            print("  spw      = {0}".format(spw))
            print("  imsize   = {0}".format(IMSIZE))
            print("  cell     = {0}".format(cell))
            print("  imagename= {0}".format(imagename))

            try:
                tclean(
                    vis=vis,
                    field=TARGET,
                    spw=spw,
                    pblimit=-1e-12,
                    imsize=IMSIZE,
                    cell=cell,
                    gridder="standard",
                    deconvolver="hogbom",
                    weighting="natural",
                    niter=NITER,
                    imagename=imagename,
                    interactive=False,
                )
            except RuntimeError as exc:
                if is_zero_row_selection_error(exc):
                    print("Skipping {0} {1}: selected 0 rows".format(vis, band))
                    continue
                raise

            exportfits(
                imagename=imagename + ".image",
                fitsimage=fitsname,
                overwrite=True,
            )


main()
