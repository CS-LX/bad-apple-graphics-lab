"""Reproduce all four videos and the gallery; completed renders are reused.

    python scripts/render_all.py
    python scripts/render_all.py --force

Install requirements.txt and FFmpeg first; see README.md for setup.
"""
from pathlib import Path
import argparse,subprocess,sys,time
from fractions import Fraction
from video_common import ROOT,CREATE_NO_WINDOW,probe
from presentation import WARNING_SECONDS

WARNING_FRAMES=round(WARNING_SECONDS*30)

JOBS=[
    ('A_tree.mp4','A_quadtree_events.mp4',WARNING_FRAMES,['render_fields.py','tree']),
    ('B_sdf.mp4','B_sdf_time_derivative.mp4',WARNING_FRAMES,['render_fields.py','sdf']),
    ('C_mesh.mp4','C_delaunay_connectivity.mp4',WARNING_FRAMES,['render_mesh.py']),
    ('D_spacetime.mp4','D_spacetime_bsp.mp4',0,['render_spacetime.py']),
]

def source_frames():
    """Count expected 30 fps output frames, ignoring a longer audio tail."""
    source=ROOT/'assets/bad_apple.mp4'
    if not source.exists():
        # Existing distributed outputs can still be reused without source media.
        return 6572
    video=next(s for s in probe(source)['streams'] if s['codec_type']=='video')
    if video.get('duration'):
        return round(float(video['duration'])*30)
    rate=Fraction(video['avg_frame_rate'])
    return round(int(video['nb_frames'])*30/rate)

def complete(path,frames,audio=False):
    if not path.exists():return False
    try:
        streams=probe(path)['streams']
        s=next(s for s in streams if s['codec_type']=='video')
        valid=(int(s.get('nb_frames',0))==frames and s['width']==960 and
               s['height']==720 and Fraction(s['r_frame_rate'])==30 and
               abs(float(s['duration'])-frames/30)<.04)
        if audio:
            tracks=[s for s in streams if s['codec_type']=='audio']
            valid=valid and len(tracks)==1 and tracks[0]['codec_name']=='aac'
        return valid
    except (subprocess.CalledProcessError,ValueError,KeyError,TypeError,
            StopIteration,ZeroDivisionError):return False

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--force',action='store_true');a=p.parse_args()
    running=[];logs=[]
    frames=source_frames()
    (ROOT/'logs').mkdir(exist_ok=True)
    for name,final,intro_frames,parts in JOBS:
        if not a.force and complete(ROOT/'deliverables'/final,frames+intro_frames,audio=True):
            print('Reuse finished '+final,flush=True);continue
        if not a.force and complete(ROOT/'output'/name,frames):
            print('Reuse '+name,flush=True);continue
        log=(ROOT/'logs'/(Path(name).stem+'.log')).open('wb');logs.append(log)
        command=[sys.executable,str(ROOT/'scripts'/parts[0]),*parts[1:]]
        proc=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=CREATE_NO_WINDOW)
        running.append((name,proc));print('Rendering '+name,flush=True)
    failures=[]
    while running:
        for name,proc in running[:]:
            if proc.poll() is not None:
                if proc.returncode:failures.append((name,proc.returncode))
                print(f'{name}: exit {proc.returncode}',flush=True);running.remove((name,proc))
        if running:time.sleep(2)
    for log in logs:log.close()
    if failures:raise RuntimeError(f'Render errors: {failures}; inspect logs/')
    finish=[sys.executable,str(ROOT/'scripts/finish_videos.py')]
    if a.force:finish.append('--force')
    subprocess.run(finish,cwd=ROOT,check=True,creationflags=CREATE_NO_WINDOW)

if __name__=='__main__':main()
