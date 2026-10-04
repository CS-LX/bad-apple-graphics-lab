"""Validate release timing, silent static warning cards, picture and audio sync.

    python scripts/validate_release.py

The four complete videos are decoded. Missing silent intermediates only skip
the optional body-frame reference check; release metadata, card stability,
source-audio alignment, and decode checks still run after output/ is cleaned.
"""
from pathlib import Path
import argparse
import datetime
import json
import math
import subprocess
import time
from fractions import Fraction
from video_common import ROOT, FFMPEG, CREATE_NO_WINDOW, probe
import numpy as np
from PIL import Image
from scipy.signal import correlate

FPS=30
SOURCE_FRAMES=6572
WARNING_FRAMES=150
RATE=8000
ITEMS=[
    ('A','A_quadtree_events.mp4','A_tree.mp4'),
    ('B','B_sdf_time_derivative.mp4','B_sdf.mp4'),
    ('C','C_delaunay_connectivity.mp4','C_mesh.mp4'),
    ('D','D_spacetime_bsp.mp4','D_spacetime.mp4'),
]

def ffmpeg(args):
    command=[FFMPEG,'-hide_banner','-loglevel','error',*map(str,args)]
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          creationflags=CREATE_NO_WINDOW,timeout=600)
    if result.returncode:
        error=result.stderr.decode('utf8','replace')[-5000:]
        raise RuntimeError(f'FFmpeg exited {result.returncode}: {error}')
    if result.stderr:
        raise RuntimeError(result.stderr.decode('utf8','replace')[-5000:])
    return result.stdout

def metadata(path,expected_frames,size=(960,720)):
    info=probe(path)
    videos=[s for s in info['streams'] if s.get('codec_type')=='video']
    audios=[s for s in info['streams'] if s.get('codec_type')=='audio']
    assert len(videos)==1,'Expected exactly one video stream'
    video=videos[0]
    assert (video['width'],video['height'])==size,'Unexpected video size'
    assert Fraction(video['r_frame_rate'])==FPS,'Unexpected frame rate'
    assert int(video['nb_frames'])==expected_frames,'Unexpected frame count'
    assert abs(float(video['duration'])-expected_frames/FPS)<.04,'Unexpected duration'
    assert len(audios)==1 and audios[0]['codec_name']=='aac','Expected one AAC audio stream'
    return {'status':'passed','frames':int(video['nb_frames']),
            'fps':FPS,'width':size[0],'height':size[1],
            'video_duration_seconds':float(video['duration']),
            'audio_duration_seconds':float(audios[0]['duration']),
            'bytes':path.stat().st_size}

def decode_complete(path):
    began=time.perf_counter()
    ffmpeg(['-xerror','-threads','2','-i',path,'-map','0:v:0','-map','0:a:0',
            '-f','null','-'])
    return {'status':'passed','exit_code':0,'error_log':'',
            'wall_seconds':round(time.perf_counter()-began,3)}

def frames(path,indices):
    indices=sorted(set(indices))
    expression='+'.join(f'eq(n,{i})' for i in indices)
    raw=ffmpeg(['-threads','2','-i',path,'-an','-sn',
                '-vf',f"select='{expression}'",'-fps_mode','passthrough',
                '-frames:v',len(indices),'-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    pixels=np.frombuffer(raw,np.uint8)
    expected=len(indices)*960*720*3
    assert pixels.size==expected,f'Expected {expected} RGB bytes, got {pixels.size}'
    decoded=pixels.reshape(len(indices),720,960,3)
    return {n:decoded[i] for i,n in enumerate(indices)}

def difference(a,b):
    delta=a.astype(np.float32)-b.astype(np.float32)
    mse=float(np.mean(delta*delta))
    return {'mae':float(np.mean(np.abs(delta))),
            'psnr_db':float(10*math.log10(255**2/mse)) if mse else 100.0}

def warning_check(decoded,intermediates):
    static=[difference(decoded[0],decoded[n]) for n in (75,149)]
    assert max(d['mae'] for d in static)<.7,f'Warning card is not static: {static}'
    card=intermediates/'warning_960x720.png'
    if card.is_file():
        reference=np.asarray(Image.open(card).convert('RGB'))
        method='Saved warning PNG, full-resolution RGB'
        similarity=difference(decoded[0],reference)
        assert similarity['mae']<2.0,f'Card differs from saved warning PNG: {similarity}'
    else:
        # Font availability may differ on another computer. Compare the
        # low-frequency layout/colors to the same generated warning design.
        from presentation import warning_card
        generated=warning_card().resize((64,48),Image.Resampling.LANCZOS)
        reduced=Image.fromarray(decoded[0]).resize((64,48),Image.Resampling.LANCZOS)
        similarity=difference(np.asarray(reduced),np.asarray(generated))
        method='Regenerated warning design at 64x48; tolerates font rasterization differences'
        assert similarity['mae']<5.0,f'Card layout differs from warning design: {similarity}'
    transition=difference(decoded[149],decoded[150])
    assert transition['mae']>3.0,'Frame 150 still resembles the warning card'
    return {'status':'passed','checked_frame_indices':[0,75,149],
            'static_differences_from_frame_0':static,'reference':method,
            'reference_difference':similarity,'frame_149_to_150_difference':transition,
            'limits':{'static_mae_max':.7,'saved_card_mae_max':2.0,
                      'regenerated_card_layout_mae_max':5.0}}

def body_check(decoded,path):
    if not path.is_file():
        return {'status':'skipped','reason':'Silent intermediate absent; release-only checks still run'}
    original=frames(path,[0,1529,1530,1531])
    first=difference(decoded[150],original[0])
    correct=difference(decoded[1680],original[1530])
    neighbours={str(i-1530):difference(decoded[1680],original[i]) for i in (1529,1530,1531)}
    assert first['mae']<4.0,f'First body frame differs from original frame zero: {first}'
    assert correct['mae']<4.0 and correct['psnr_db']>30.0,f'Body frame alignment/image mismatch: {correct}'
    assert (correct['mae']<=min(neighbours['-1']['mae'],neighbours['1']['mae'])+.15), \
        'Expected source frame is not the closest temporal match'
    return {'status':'passed','first_body_frame_index':150,
            'first_frame_difference':first,'source_frame_index':1530,
            'release_frame_index':1680,'source_seconds':51,'release_seconds':56,
            'difference':correct,'adjacent_source_frame_differences':neighbours,
            'limits':{'mae_max':4.0,'psnr_db_min':30.0,'closest_frame_mae_tolerance':.15}}

def pcm(path):
    return np.frombuffer(ffmpeg(['-threads','1','-i',path,'-map','0:a:0','-vn',
                               '-ac','1','-ar',RATE,'-f','f32le','pipe:1']),np.float32)

def audio_hash(path):
    return ffmpeg(['-i',path,'-map','0:a:0','-c:a','copy','-f','hash',
                   '-hash','sha256','pipe:1']).decode().strip()

def correlation(a,b,max_lag=80):
    n=min(len(a),len(b))
    a=a[:n].astype(np.float32);b=b[:n].astype(np.float32)
    a-=a.mean();b-=b.mean()
    energy=math.sqrt(float(np.dot(a,a))*float(np.dot(b,b)))
    assert energy>1e-8,'Not enough non-silent audio to measure correlation'
    result=correlate(a,b,mode='full',method='fft')
    center=n-1
    region=result[center-max_lag:center+max_lag+1]
    lag=int(np.argmax(region))-max_lag
    return {'zero_lag_correlation':float(result[center]/energy),
            'peak_lag_samples':lag,'peak_lag_seconds':lag/RATE,
            'searched_lag_samples':[-max_lag,max_lag],'compared_samples':n}

def audio_check(path,source_pcm):
    audio=pcm(path)
    silence=audio[:5*RATE]
    body=audio[5*RATE:]
    rms=float(np.sqrt(np.mean(silence**2)))
    peak=float(np.max(np.abs(silence)))
    reference_rms=float(np.sqrt(np.mean(source_pcm**2)))
    maximum_rms=max(1e-4,.01*reference_rms)
    assert len(silence)==5*RATE,'Missing warning audio interval'
    assert rms<=maximum_rms,f'Warning audio is not near silence: RMS {rms}'
    assert abs(len(body)-len(source_pcm))<=RATE*.1,'Audio body length differs by more than 0.1 seconds'
    global_result=correlation(body,source_pcm)
    assert global_result['zero_lag_correlation']>.98,f'Audio does not match source: {global_result}'
    assert global_result['peak_lag_samples']==0,f'Audio timing offset: {global_result}'
    windows=[]
    for start in (1,51,101,151,199):
        lo,hi=start*RATE,(start+10)*RATE
        if hi<=min(len(body),len(source_pcm)):
            segment=correlation(body[lo:hi],source_pcm[lo:hi])
            segment['source_start_seconds']=start
            assert (segment['zero_lag_correlation']>.98 and segment['peak_lag_samples']==0), \
                f'Audio drift/content mismatch in window: {segment}'
            windows.append(segment)
    return {'status':'passed','decoded_rate_hz':RATE,'channels':1,
            'removed_intro_samples':5*RATE,'intro_rms':rms,'intro_peak':peak,
            'intro_rms_dbfs':20*math.log10(rms) if rms>0 else -200.0,
            'intro_rms_limit':maximum_rms,'global':global_result,'windows':windows,
            'source_samples':len(source_pcm),'body_samples':len(body)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'assets/bad_apple.mp4')
    parser.add_argument('--deliverables',type=Path,default=ROOT/'deliverables')
    parser.add_argument('--intermediates',type=Path,default=ROOT/'output')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    report_path=args.report or args.deliverables/'release_qa.json'
    report={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status':'running','files':{},'failed_checks':[],
            'limits':[
                'This checks file integrity and sampled visual/audio alignment, not medical safety.',
                'Warning text is compared visually to the generated design; no OCR is performed.',
                'After deleting output/, warning layout is regenerated and compared at low resolution to tolerate local fonts; body-reference checks are skipped.',
                'Lossy H.264 and AAC transcoding are allowed; RGB thresholds and PCM correlation are quantitative tolerances.',
                'Audio lag is measured after mono 8 kHz decoding at 0.125 ms resolution, within a +/-10 ms search, globally and in five ten-second windows.',
                'The comparison video is checked only for metadata and freshness here; it is not fully decoded by this script.'
            ]}
    def check(label,fn):
        try:
            result=fn()
            print(label+': '+result['status'],flush=True)
            return result
        except Exception as error:
            report['failed_checks'].append(label)
            print(label+': FAILED '+str(error),flush=True)
            return {'status':'failed','error':str(error),'error_type':type(error).__name__}
    reference_audio=None
    source_hash=None
    source_error=None
    try:
        reference_audio=pcm(args.source)
        source_hash=audio_hash(args.source)
    except Exception as error:
        source_error=str(error)
    for letter,name,original in ITEMS:
        path=args.deliverables/name
        entry={'file':str(path)}
        report['files'][letter]=entry
        count=SOURCE_FRAMES+(WARNING_FRAMES if letter!='D' else 0)
        entry['metadata']=check(letter+' metadata',lambda:metadata(path,count))
        entry['full_decode']=check(letter+' full decode',lambda:decode_complete(path))
        if letter!='D':
            decoded=None
            try:
                decoded=frames(path,[0,75,149,150,1680])
            except Exception as error:
                report['failed_checks'].append(letter+' frame extraction')
                entry['frame_extraction']={'status':'failed','error':str(error)}
            if decoded is not None:
                entry['warning']=check(letter+' warning',lambda:warning_check(decoded,args.intermediates))
                entry['body_alignment']=check(letter+' body alignment',lambda:body_check(decoded,args.intermediates/original))
            if source_error:
                report['failed_checks'].append(letter+' source audio')
                entry['audio_alignment']={'status':'failed','error':source_error}
            else:
                entry['audio_alignment']=check(letter+' audio alignment',lambda:audio_check(path,reference_audio))
        else:
            def copied_audio():
                if source_error:raise RuntimeError(source_error)
                result=audio_hash(path)
                assert result==source_hash,'Compressed AAC packet hash differs from source'
                return {'status':'passed','method':'FFmpeg hash muxer SHA256 over copied compressed audio packets',
                        'source_hash':source_hash,'release_hash':result}
            entry['audio_copy']=check('D copied audio',copied_audio)
        report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    comparison=args.deliverables/'00_four_way_comparison.mp4'
    if comparison.exists() and all((args.deliverables/name).exists() for _,name,_ in ITEMS):
        latest=max((args.deliverables/name).stat().st_mtime for _,name,_ in ITEMS)
        if comparison.stat().st_mtime>=latest:
            report['comparison_metadata']=check('Comparison metadata',lambda:metadata(comparison,SOURCE_FRAMES+WARNING_FRAMES,(1280,960)))
        else:
            report['comparison_metadata']={'status':'skipped','reason':'Comparison predates one or more final videos'}
    else:
        report['comparison_metadata']={'status':'skipped','reason':'Comparison or required final video absent'}
    report['status']='failed' if report['failed_checks'] else 'passed'
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('Release QA '+report['status']+': '+str(report_path),flush=True)
    return 1 if report['failed_checks'] else 0

if __name__=='__main__':
    raise SystemExit(main())
