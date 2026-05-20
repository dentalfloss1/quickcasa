import argparse
import glob
import math
import os
import re
import shutil
from collections import OrderedDict


C_M_S = 299792458.0
ARCSEC_PER_RADIAN = 206264.806247
VLA_DISH_DIAMETER_M = 25.0

DEFAULT_PIXELS_PER_SYNTH_BEAM = 10.0
DEFAULT_PB_FWHM = 1.0
DEFAULT_MIN_IMSIZE = 512
DEFAULT_MAX_IMSIZE = 8192
DEFAULT_NITER = 3000

VLA_BANDS = [
    ("4", 54e6, 86e6),
    ("P", 224e6, 480e6),
    ("L", 1e9, 2e9),
    ("S", 2e9, 4e9),
    ("C", 4e9, 8e9),
    ("X", 8e9, 12e9),
    ("Ku", 12e9, 18e9),
    ("K", 18e9, 26.5e9),
    ("Ka", 26.5e9, 40e9),
    ("Q", 40e9, 50e9),
]


parser = argparse.ArgumentParser()
parser.add_argument("origvis",type=str)
parser.add_argument("--pixels-per-beam", type=float, default=DEFAULT_PIXELS_PER_SYNTH_BEAM)
parser.add_argument("--pb-fwhm", type=float, default=DEFAULT_PB_FWHM)
parser.add_argument("--min-imsize", type=int, default=DEFAULT_MIN_IMSIZE)
parser.add_argument("--max-imsize", type=int, default=DEFAULT_MAX_IMSIZE)
parser.add_argument("--niter", type=int, default=DEFAULT_NITER)
args = parser.parse_args()
origvis = args.origvis


def get_msmd():
    tool = globals().get("msmd")
    if tool is not None:
        return tool
    try:
        from casatools import msmetadata

        return msmetadata()
    except ImportError:
        from taskinit import msmdtool

        return msmdtool()


def get_tb():
    tool = globals().get("tb")
    if tool is not None:
        return tool
    try:
        from casatools import table

        return table()
    except ImportError:
        from taskinit import tbtool

        return tbtool()


def safe_remove(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.exists(path) or os.path.islink(path):
        os.remove(path)


def safe_name(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._") or "unnamed"


def unique(values):
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def band_for_frequency(freq_hz):
    for band, min_hz, max_hz in VLA_BANDS:
        if min_hz <= freq_hz < max_hz:
            return band
    return None


def spw_selection(spw_ids):
    ranges = []
    start = None
    last = None
    for spw_id in sorted(spw_ids):
        if start is None:
            start = spw_id
            last = spw_id
            continue
        if spw_id == last + 1:
            last = spw_id
            continue
        if start == last:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}~{last}")
        start = spw_id
        last = spw_id
    if start is not None:
        if start == last:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}~{last}")
    return ",".join(ranges)


def vla_band_spws(vis):
    md = get_msmd()
    groups = OrderedDict((band, []) for band, _, _ in VLA_BANDS)
    unmatched = []
    md.open(vis)
    try:
        for spw_id in range(md.nspw()):
            band = band_for_frequency(float(md.meanfreq(spw_id)))
            if band is None:
                unmatched.append(spw_id)
            else:
                groups[band].append(spw_id)
    finally:
        md.close()
    if unmatched:
        print("Ignoring SPWs outside standard VLA bands: {0}".format(spw_selection(unmatched)))
    return [(band, spw_ids) for band, spw_ids in groups.items() if spw_ids]


def field_names_for_intent(vis, intent_fragment):
    md = get_msmd()
    field_ids = []
    md.open(vis)
    try:
        fieldnames = list(md.fieldnames())
        for intent in md.intents():
            if intent_fragment.upper() not in intent.upper():
                continue
            for field_id in md.fieldsforintent(intent):
                field_ids.append(int(field_id))
        return [fieldnames[field_id] for field_id in unique(field_ids)]
    finally:
        md.close()


def required_fields_for_intents(vis):
    bandpass_fields = field_names_for_intent(vis, "CALIBRATE_BANDPASS")
    gain_fields = field_names_for_intent(vis, "CALIBRATE_PHASE")
    target_fields = field_names_for_intent(vis, "OBSERVE_TARGET#UNSPECIFIED")
    if not target_fields:
        target_fields = field_names_for_intent(vis, "OBSERVE_TARGET")

    missing = []
    if not bandpass_fields:
        missing.append("CALIBRATE_BANDPASS")
    if not gain_fields:
        missing.append("CALIBRATE_PHASE")
    if not target_fields:
        missing.append("OBSERVE_TARGET#UNSPECIFIED")
    if missing:
        raise RuntimeError("Could not find required scan intents in {0}: {1}".format(vis, ", ".join(missing)))

    bfield = bandpass_fields[0]
    fluxfield = bfield
    gfield = gain_fields[0]
    print("Auto-selected fields from scan intents:")
    print("  bandpass = {0}".format(bfield))
    print("  fluxcal  = {0}".format(fluxfield))
    print("  gaincal  = {0}".format(gfield))
    print("  target   = {0}".format(", ".join(target_fields)))
    return target_fields, gfield, fluxfield, bfield


def band_ms_name(band):
    return "{0}band.ms".format(band)


def all_spw_ids(vis):
    md = get_msmd()
    md.open(vis)
    try:
        return list(range(md.nspw()))
    finally:
        md.close()


def mean_frequency_hz(vis, spw_ids):
    md = get_msmd()
    md.open(vis)
    try:
        freqs = [float(md.meanfreq(spw_id)) for spw_id in spw_ids]
    finally:
        md.close()
    return sum(freqs) / float(len(freqs))


def max_baseline_m(vis):
    tbtool = get_tb()
    tbtool.open(os.path.join(vis, "ANTENNA"))
    try:
        positions = tbtool.getcol("POSITION")
    finally:
        tbtool.close()

    nant = positions.shape[1]
    max_bl = 0.0
    for i in range(nant):
        xi, yi, zi = positions[:, i]
        for j in range(i + 1, nant):
            xj, yj, zj = positions[:, j]
            baseline = math.sqrt((xi - xj) ** 2 + (yi - yj) ** 2 + (zi - zj) ** 2)
            max_bl = max(max_bl, baseline)
    if max_bl <= 0.0:
        raise RuntimeError("Could not compute a valid maximum baseline for {0}".format(vis))
    return max_bl


def is_good_imsize(value):
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


def auto_tclean_params(vis):
    spw_ids = all_spw_ids(vis)
    freq_hz = mean_frequency_hz(vis, spw_ids)
    wavelength_m = C_M_S / freq_hz
    synth_beam_arcsec = wavelength_m / max_baseline_m(vis) * ARCSEC_PER_RADIAN
    cell_arcsec = synth_beam_arcsec / args.pixels_per_beam
    pb_arcsec = 1.02 * wavelength_m / VLA_DISH_DIAMETER_M * ARCSEC_PER_RADIAN
    raw_imsize = pb_arcsec * args.pb_fwhm / cell_arcsec
    bounded_imsize = max(args.min_imsize, min(args.max_imsize, raw_imsize))
    return "{0:.6f}arcsec".format(cell_arcsec), next_good_imsize(bounded_imsize)


target_fields, gfield, fluxfield, bfield = required_fields_for_intents(origvis)
target = ",".join(target_fields)

split_vis = []
for band, spw_ids in vla_band_spws(origvis):
    outputvis = band_ms_name(band)
    for f in [outputvis, outputvis + ".flagversions"]:
        safe_remove(f)
    print("Splitting VLA {0} band SPWs {1} to {2}".format(band, spw_selection(spw_ids), outputvis))
    split(origvis, spw=spw_selection(spw_ids), outputvis=outputvis, datacolumn='ALL')
    split_vis.append((outputvis, "{0}band".format(band)))

if not split_vis:
    raise RuntimeError("No standard VLA observing bands were found in {0}".format(origvis))



# Remove files from previous runs, glob ensures we only delete it if it exists.
for pattern in [
    'gaincalspw*',
    '*target*spw*',
    '*jpg',
    '*delay*K*',
    '*bp*B*',
    '*gain*G*',
    '*pol*D*',
    '*flux*fluxscale*',
]:
    for f in glob.glob(pattern):
        safe_remove(f)

for visname, spw in split_vis:
    md = get_msmd()
    md.open(visname)
    try:
        nchan = len(md.chanfreqs(0))
        referenceant = md.antennanames()[0]
        bfieldno = md.fieldsforname(bfield)[0]
    finally:
        md.close()
    if bfield!=fluxfield:
        calfields = unique([bfield,gfield,fluxfield])
        allfields= unique([bfield,gfield,target,fluxfield])
    else:
        calfields = unique([bfield,gfield])
        allfields= unique([bfield,gfield,target])
    minbaselines=3
    kfilebase = f'delayspw{spw}.K'
    bfilebase = f'bpspw{spw}.B'
    gfilebase = f'gainspw{spw}.G'
    pregfilebase = f'gainspw{spw}.Gpre'
    fluxfilebase = f'fluxspw{spw}.fluxscale'
    polfilebase = f'polspw{spw}.D'
    if fluxfield in ['J0408-6545','0408-6545']:
        setjy(vis=visname,field=fluxfield,scalebychan=True, standard="manual",fluxdensity=[17.066,0.0,0.0,0.0],spix=[-1.179],reffreq="1284MHz")
    else:
        setjy(vis=visname,field=fluxfield,scalebychan=True)
    # flagdata(vis=visname, mode='manual',scan='0,44')
    # RFI issues in this one
    flagdata(vis=visname, mode='shadow')
    for f in calfields:
        flagdata(vis=visname, mode='tfcrop', field=f,
                ntime='scan', timecutoff=5.0, freqcutoff=5.0, timefit='line',
                freqfit='line', extendflags=False, timedevscale=5., freqdevscale=5.,
                extendpols=True, growaround=False, action='apply', flagbackup=True,
                overwrite=True, writeflags=True, datacolumn='DATA')
    plotms(vis=visname, xaxis='freq', yaxis='amp', showgui=False,
            field=bfield, plotfile=f'{spw}freqampbfield.jpg')
    plotms(vis=visname, xaxis='freq', yaxis='amp', showgui=False,
            field=gfield, plotfile=f'{spw}freqampgfield.jpg')
    plotms(vis=visname, xaxis='time', yaxis='amp', showgui=False,
            field=bfield, plotfile=f'{spw}timeampbfield.jpg')
    plotms(vis=visname, xaxis='time', yaxis='amp', showgui=False,
            field=gfield, plotfile=f'{spw}timeampgfield.jpg') 
    flagdata(vis=visname, mode='tfcrop', field=target,
            ntime='scan', timecutoff=6.0, freqcutoff=6.0, timefit='poly',
            freqfit='poly', extendflags=False, timedevscale=5., freqdevscale=5.,
            extendpols=True, growaround=False, action='apply', flagbackup=True,
            overwrite=True, writeflags=True, datacolumn='DATA')
    
    flagdata(vis=visname, mode='extend', field=target,
            datacolumn='data', clipzeros=True, ntime='scan', extendflags=False,
            extendpols=True, growtime=80., growfreq=80., growaround=False,
            flagneartime=False, flagnearfreq=False, action='apply',
            flagbackup=True, overwrite=True, writeflags=True)
    for f in calfields:
        # Conservatively extend flags for all fields in config
        flagdata(vis=visname, mode='extend', field=f,
                datacolumn='data', clipzeros=True, ntime='scan', extendflags=False,
                extendpols=True, growtime=80., growfreq=80., growaround=False,
                flagneartime=False, flagnearfreq=False, action='apply',
                flagbackup=True, overwrite=True, writeflags=True)
    kfile = f'{kfilebase}'
    kxfile = f'{kfilebase}x'
    bfile = f'{bfilebase}'
    pregfile = f'{pregfilebase}'
    gfile = f'{gfilebase}'
    fluxfile = f'{fluxfilebase}'
    polfile = f'{polfilebase}'

    append=False
    gaincal(vis=visname, caltable = pregfile, field = bfield, refant = referenceant,
                minblperant = minbaselines, solnorm = False,  gaintype = 'G',
                solint = "int", combine = '', calmode='p',
                parang = False,append = append)
    plotms(vis=pregfile, xaxis='time', yaxis='phase', coloraxis='corr', 
                field=bfield, iteraxis='antenna',plotrange=[-1,-1,-180,180],
                showgui= False, gridrows=3, gridcols=2, plotfile=f'{spw}initialgain.jpg')
    gaincal(vis=visname, caltable = kfile, field = bfield, refant = referenceant,
                minblperant = minbaselines, solnorm = False,  gaintype = 'K',
                solint = "int", combine = '', parang = False,append = False)
    bandpass(vis=visname, caltable = bfile,
            field = bfield, refant = referenceant,
            minblperant = minbaselines, solnorm = False,  solint = "int",
            combine = '', bandtype = 'B', fillgaps = 4,
            gaintable = [kfile], gainfield = bfield,
            parang = False, append = append)
    gaincal(vis=visname, caltable = kxfile, field=gfield, refant=referenceant,
            gaintype='KCROSS', smodel=[1.,0.,1.,0.], solint='inf', combine='scan',
            minblperant=minbaselines, minsnr=0, gaintable=[kfile,bfile],gainfield=[bfield,bfield])
    gaincal(vis=visname, caltable = gfile,
            field = fluxfield, refant = referenceant,
            minblperant = minbaselines, solnorm = False,  gaintype = 'G',
            solint = "int", combine = '', calmode='ap',
            gaintable=[kfile,bfile,kxfile],gainfield=[bfield,bfield,gfield],
            parang = False, append = False)
    if fluxfield!=bfield:
        gaincal(vis=visname, caltable = gfile,
                field = bfield, refant = referenceant,
                minblperant = minbaselines, solnorm = False,  gaintype = 'G',
                solint = "int", combine = '', calmode='ap',
                gaintable=[kfile,bfile,kxfile],gainfield=[bfield,bfield,gfield],
                parang = False, append = True)
    gaincal(vis=visname, caltable = gfile,
            field = gfield, refant = referenceant,
            minblperant = minbaselines, solnorm = False,  gaintype = 'G',
            solint = "int", combine = '', calmode='ap',
            gaintable=[kfile,bfile,kxfile],gainfield=[bfield,bfield,gfield],
            parang = False, append = True)
    polcal(vis=visname,caltable=polfile,field=bfield,refant=referenceant,gaintable=[bfile,kxfile,gfile],poltype='D',solint='inf')
    plotms(vis=gfile,xaxis='time',yaxis='amp',coloraxis='corr',iteraxis='antenna',gridrows=3,gridcols=2,showgui=False,
            plotfile=f'relpolgaintable{spw}.jpg')
    kfile2 = f'{kfilebase}1'
    kxfile2 = f'{kfilebase}x1'
    bfile2 = f'{bfilebase}1'
    pregfile2 = f'{pregfilebase}1'
    gfile2 = f'{gfilebase}1'
    fluxfile2 = f'{fluxfilebase}1'
    polfile2 = f'{polfilebase}1'
    gaincal(vis=visname, caltable = pregfile2, field = bfield, refant = referenceant,
                minblperant = minbaselines, solnorm = False,  gaintype = 'G',
                solint = "int", combine = '', calmode='p',
                parang = False,append = append, gaintable=[bfile,kxfile,gfile,polfile])
    plotms(vis=pregfile2, xaxis='time', yaxis='phase', coloraxis='corr', 
                field=bfield, iteraxis='antenna',plotrange=[-1,-1,-180,180],
                showgui= False, gridrows=3, gridcols=2, plotfile=f'{spw}initialgain2.jpg')
    bandpass(vis=visname, caltable = bfile2,
            field = bfield, refant = referenceant,
            minblperant = minbaselines, solnorm = False,  solint = 60,
            combine = '', bandtype = 'B', fillgaps = 4,
            gaintable = [gfile,polfile], gainfield = [bfield,bfield],
            parang = False, append = append)
    gaincal(vis=visname, caltable = gfile2,
            field = fluxfield, refant = referenceant,
            minblperant = minbaselines, solnorm = False,  gaintype = 'G',
            solint = "int", combine = '', calmode='ap',
            gaintable=bfile2,
            parang = False, append = False)
    if fluxfield!=bfield:
        gaincal(vis=visname, caltable = gfile2,
                field = bfield, refant = referenceant,
                minblperant = minbaselines, solnorm = False,  gaintype = 'G',
                solint = "int", combine = '', calmode='ap',
                gaintable=bfile2,
                parang = False, append = True)
    gaincal(vis=visname, caltable = gfile2,
            field = gfield, refant = referenceant,
            minblperant = minbaselines, solnorm = False,  gaintype = 'G',
            solint = "int", combine = '', calmode='ap',
            gaintable=bfile2,
            parang = False, append = True)
    polcal(vis=visname,caltable=polfile2,field=bfield,refant=referenceant,gaintable=[bfile2,gfile2],poltype='D',solint='inf')
    if fluxfield!=bfield:
        myscale = fluxscale(vis=visname,caltable=gfile2,fluxtable=fluxfile2, reference=fluxfield,transfer=[gfield,bfield],incremental=False, fitorder=1)
    else:
        myscale = fluxscale(vis=visname,caltable=gfile2,fluxtable=fluxfile2, reference=fluxfield,transfer=[gfield],incremental=False, fitorder=1)
    applycal(vis=visname, field=fluxfield,
            selectdata=False, calwt=False, gaintable=[fluxfile2,bfile2,polfile2],
            gainfield=[fluxfield,'',''],
            parang=True, interp=['linear','',''])
    applycal(vis=visname, field=gfield,
            selectdata=False, calwt=False, gaintable=[fluxfile2,bfile2,polfile2],
            gainfield=[gfield,'',''],
            parang=True, interp=['linear','',''])
    if fluxfield!=bfield:
        applycal(vis=visname, field=bfield,
                selectdata=False, calwt=False, gaintable=[fluxfile2,bfile2,polfile2],
                gainfield=[gfield,'',''],
                parang=True, interp=['linear','',''])
    
    applycal(vis=visname, field=target,
            selectdata=False, calwt=False, gaintable=[fluxfile2,bfile2,polfile2],
            gainfield=[gfield,'',''],
            parang=True, interp=['linear',''])
    
    
    # now flag using 'rflag' option  for flux, phase cal and extra fields tight flagging
    for f in calfields:
        flagdata(vis=visname, mode="tfcrop", datacolumn="corrected",
                field=f, ntime="scan", timecutoff=6.0,
                freqcutoff=5.0, timefit="line", freqfit="line",
                flagdimension="freqtime", extendflags=False, timedevscale=5.0,
                freqdevscale=5.0, extendpols=False, growaround=False,
                action="apply", flagbackup=True, overwrite=True, writeflags=True)
        flagdata(vis=visname, mode="rflag", datacolumn="corrected",
                field=f, timecutoff=5.0, freqcutoff=5.0,
                timefit="poly", freqfit="line", flagdimension="freqtime",
                extendflags=False, timedevscale=4.0, freqdevscale=4.0,
                spectralmax=500.0, extendpols=False, growaround=False,
                flagneartime=False, flagnearfreq=False, action="apply",
                flagbackup=True, overwrite=True, writeflags=True)
    
        ## Now extend the flags (70% more means full flag, change if required)
        flagdata(vis=visname, mode="extend", field=f,
                datacolumn="corrected", clipzeros=True, ntime="scan",
                extendflags=False, extendpols=False, growtime=90.0, growfreq=90.0,
                growaround=False, flagneartime=False, flagnearfreq=False,
                action="apply", flagbackup=True, overwrite=True, writeflags=True)
    
    # Now flag for target - moderate flagging, more flagging in self-cal cycles
    flagdata(vis=visname, mode="tfcrop", datacolumn="corrected",
            field=target, ntime='scan', timecutoff=6.0, freqcutoff=5.0,
            timefit="poly", freqfit="line", flagdimension="freqtime",
            extendflags=False, timedevscale=5.0, freqdevscale=5.0,
            extendpols=False, growaround=False, action="apply", flagbackup=True,
            overwrite=True, writeflags=True)
    for i in range(3): 
    # now flag using 'rflag' option
        flagdata(vis=visname, mode="rflag", datacolumn="corrected",
                field=target, timecutoff=5.0, freqcutoff=5.0, timefit="poly",
                freqfit="poly", flagdimension="freqtime", extendflags=False,
                timedevscale=5.0, freqdevscale=5.0, spectralmax=500.0,
                extendpols=False, growaround=False, flagneartime=False,
                flagnearfreq=False, action="apply", flagbackup=True, overwrite=True,
                writeflags=True, ntime='scan')
    for i in range(3): 
    # now flag using 'rflag' option
        flagdata(vis=visname, mode="rflag", datacolumn="corrected",
                field=target, timecutoff=4.0, freqcutoff=4.0, timefit="poly",
                freqfit="poly", flagdimension="freqtime", extendflags=False,
                timedevscale=4.0, freqdevscale=4.0, spectralmax=500.0,
                extendpols=False, growaround=False, flagneartime=False,
                flagnearfreq=False, action="apply", flagbackup=True, overwrite=True,
                writeflags=True, ntime='scan')
    for i in range(3): 
    # now flag using 'rflag' option
        flagdata(vis=visname, mode="rflag", datacolumn="corrected",
                field=target, timecutoff=3.0, freqcutoff=3.0, timefit="poly",
                freqfit="poly", flagdimension="freqtime", extendflags=False,
                timedevscale=3.0, freqdevscale=3.0, spectralmax=500.0,
                extendpols=False, growaround=False, flagneartime=False,
                flagnearfreq=False, action="apply", flagbackup=True, overwrite=True,
                writeflags=True, ntime='scan')
# Image each split band with cell/imsize derived from the MS frequencies and antenna layout.
for v, band_label in split_vis:
    cell, imsize = auto_tclean_params(v)
    print("Auto tclean parameters for {0}: cell={1}, imsize={2}".format(v, cell, imsize))
    for target_field in target_fields:
        imagename = "targetspw{0}_{1}".format(band_label, safe_name(target_field))
        tclean(vis=v, field=target_field, spw='', datacolumn='corrected',
               imagename=imagename, imsize=imsize, cell=cell,
               gridder='standard', pblimit=-1e-12, specmode='mfs',
               deconvolver='mtmfs', nterms=2, weighting='natural',
               niter=args.niter, gain=0.1, pbcor=True)
