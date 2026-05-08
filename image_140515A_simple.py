import glob
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
PIXELS_PER_SYNTH_BEAM = 10.0
NITER = 5000

VLA_BANDS_GHZ = {
    "P": (0.230, 0.470),
    "L": (1.000, 2.000),
    "S": (2.000, 4.000),
    "C": (4.000, 8.000),
    "X": (8.000, 12.000),
    "Ku": (12.000, 18.000),
    "K": (18.000, 26.500),
    "Ka": (26.500, 40.000),
    "Q": (40.000, 50.000),
}


def band_for_frequency(freq_hz):
    freq_ghz = freq_hz / 1.0e9
    for band, limits in VLA_BANDS_GHZ.items():
        if limits[0] <= freq_ghz < limits[1]:
            return band
    return None


def field_exists(vis, field_name):
    msmd.open(vis)
    try:
        return field_name in list(msmd.fieldnames())
    finally:
        msmd.close()


def spws_by_band(vis, field_name):
    msmd.open(vis)
    try:
        field_id = list(msmd.fieldnames()).index(field_name)
        spws = list(msmd.spwsforfield(field_id))
        by_band = {}
        for spw in spws:
            chan_freqs = msmd.chanfreqs(spw)
            if len(chan_freqs):
                mean_freq = sum(chan_freqs) / float(len(chan_freqs))
                band = band_for_frequency(mean_freq)
                if band is not None:
                    by_band.setdefault(band, {"spws": [], "freqs": []})
                    by_band[band]["spws"].append(spw)
                    by_band[band]["freqs"].append(mean_freq)
        if not by_band:
            raise RuntimeError("No channel frequencies found for {0}".format(vis))
        return by_band
    finally:
        msmd.close()


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


def cell_from_antennas(vis, freq_hz):
    c_m_s = 299792458.0
    wavelength_m = c_m_s / freq_hz
    beam_rad = wavelength_m / max_baseline_m(vis)
    cell_arcsec = beam_rad * 206264.806247 / PIXELS_PER_SYNTH_BEAM
    return "{0:.6f}arcsec".format(cell_arcsec)


def image_name_for_ms(vis, band):
    base = os.path.basename(vis)
    if base.endswith(".ms"):
        base = base[:-3]
    return os.path.join("images", base + "_" + TARGET + "_" + band)


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

        for band, band_data in sorted(spws_by_band(vis, TARGET).items()):
            freq_hz = sum(band_data["freqs"]) / float(len(band_data["freqs"]))
            spw = ",".join(str(s) for s in sorted(band_data["spws"]))
            cell = cell_from_antennas(vis, freq_hz)
            imagename = image_name_for_ms(vis, band)
            fitsname = imagename + ".fits"

            print("")
            print("Imaging {0}".format(vis))
            print("  field    = {0}".format(TARGET))
            print("  band     = {0}".format(band))
            print("  spw      = {0}".format(spw))
            print("  imsize   = {0}".format(IMSIZE))
            print("  cell     = {0}".format(cell))
            print("  imagename= {0}".format(imagename))

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

            exportfits(
                imagename=imagename + ".image",
                fitsimage=fitsname,
                overwrite=True,
            )


main()
