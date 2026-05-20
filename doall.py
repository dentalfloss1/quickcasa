import os
import glob
import shutil
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("origvis",type=str)
args = parser.parse_args()
origvis = args.origvis
for f in glob.glob('2GHz*.ms*'):
    shutil.rmtree(f)
for f in glob.glob('5GHz*.ms*'):
    shutil.rmtree(f)
for f in glob.glob('6GHz*.ms*'):
    shutil.rmtree(f)
for f in glob.glob('9GHz*.ms*'):
    shutil.rmtree(f)
for f in glob.glob('19GHz*.ms*'):
    shutil.rmtree(f)
for f in glob.glob('34GHz*.ms*'):
    shutil.rmtree(f)

# flagdata(vis=origvis, mode='manual',field='focus')

# split(origvis, spw='0~1', outputvis = '19GHz.ms',datacolumn='ALL')

split(origvis, spw='34~65', outputvis = '6GHz.ms',datacolumn='ALL')
# vis = '5GHz.ms'
# 
# 
# split(origvis, spw='3', outputvis = '9GHz.ms',datacolumn='ALL')
# vis = '9GHz.ms'


# split(origvis, spw='4', outputvis = '2GHz.ms',datacolumn='ALL')




 # Remove files from previous runs, glob ensures we only delete it if it exists
for f in glob.glob('gaincalspw*'):
    shutil.rmtree(f)
for f in glob.glob('*target*spw*'):
    shutil.rmtree(f)
for f in glob.glob(f'*jpg'):
    os.remove(f)
for f in glob.glob(f'*delay*K*'):
    shutil.rmtree(f)
for f in glob.glob(f'*bp*B*'):
    shutil.rmtree(f)
for f in glob.glob(f'*gain*G*'):
    shutil.rmtree(f)
for f in glob.glob(f'*pol*D*'):
    shutil.rmtree(f)
for f in glob.glob(f'*flux*fluxscale*'):
    shutil.rmtree(f)
for visname in ['6GHz.ms']:
    spw = visname[:-3]
    msmd.open(origvis)
    nchan = len(msmd.chanfreqs(0))
    referenceant = msmd.antennanames()[0]
    # Change field names
    target = "GRB251003A"
    gfield = "J0102+5824"
    fluxfield = "3C48"
    bfield = fluxfield
    if bfield!=fluxfield:
        calfields = [bfield,gfield,fluxfield]
        allfields= [bfield,gfield,target,fluxfield]
    else:
        calfields = [bfield,gfield]
        allfields= [bfield,gfield,target]
    bfieldno = msmd.fieldsforname(bfield)[0]
    msmd.close()
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
                showgui= False, gridrows=3, gridcols=2, plotfile='initialgain.jpg')
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
                showgui= False, gridrows=3, gridcols=2, plotfile='initialgain2.jpg')
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
# Change resolution, this is for an extended config, if in more compact config, try doing 10x bigger resolution

cell=["0.15arcsec"]
imsize=5120
spw=[""]
freqs = ["6GHz","9.0GHz"]
vis=["6GHz.ms"]
for c,s,f,v in zip(cell,spw,freqs,vis):
    tclean( vis=v,field=target,spw=s,datacolumn='corrected',imagename=f'targetspw{f}',imsize=imsize,cell=c,gridder='standard',pblimit=-1e-12,deconvolver='mtmfs',nterms=2,weighting='natural',niter=3000,gain=0.1,pbcor=True)


