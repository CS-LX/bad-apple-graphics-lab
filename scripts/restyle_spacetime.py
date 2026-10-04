"""One-time migration of legacy D HUDs; not part of normal video generation.

Current render_spacetime.py output is already clean. Do not run this tool on
current renders as an everyday processing step; it is retained for legacy files.

The top/bottom HUDs occupy empty margins. A 94x10 px strip where the old TIME
glyph grazed the far volume edge is restored from the exact original BSP, not
painted out. This also preserves geometry when the source has a white border.
"""
from pathlib import Path
from collections import deque
import argparse,json,subprocess,time
import numpy as np
from PIL import Image,ImageDraw
from video_common import FFMPEG, FFPROBE, CREATE_NO_WINDOW
from render_spacetime import ROOT,W,H,CHUNK,LOOK,DATA_FPS,OUTPUT_FPS,BASE,COLORS,partition,point

PATCH=(758,104,852,114)

def restore_patch(leaves,now):
    xleft,ytop,xright,ybottom=PATCH
    patch=BASE.crop(PATCH);d=ImageDraw.Draw(patch)
    candidates=[]
    def p(x,y,t):
        px,py=point(x,y,t)
        return px-xleft,py-ytop
    for x0,x1,y0,y1,t0,t1 in leaves:
        if t1<=now or t0>=now+LOOK:continue
        a=max(t0,now)-now;z=min(t1,now+LOOK)-now
        if point(x0,y0,z)[1]>=ybottom:continue
        if point(x1,y1,z)[0]<xleft:continue
        if point(x0,y0,a)[0]>=xright:continue
        candidates.append(((a+z)*.5-.28*(x0+x1)*.5+.1*(y0+y1)*.5,(x0,x1,y0,y1,a,z,t1-t0)))
    candidates.sort(key=lambda v:v[0],reverse=True)
    for _,(x0,x1,y0,y1,a,z,duration) in candidates:
        c,top,side,edge=COLORS[duration]
        a00=p(x0,y0,a);a10=p(x1,y0,a);a11=p(x1,y1,a);a01=p(x0,y1,a)
        z00=p(x0,y0,z);z10=p(x1,y0,z);z11=p(x1,y1,z)
        d.polygon((a00,a10,z10,z00),fill=top,outline=edge)
        d.polygon((a10,a11,z11,z10),fill=side,outline=edge)
        d.polygon((a00,a10,a11,a01),fill=c,outline=edge)
    return patch

def restyle(rgb,leaves,now):
    image=Image.fromarray(rgb)
    # Geometry is bounded by y=104..676. Only empty outer margins are replaced.
    image.paste(BASE.crop((0,0,960,104)),(0,0))
    image.paste(BASE.crop((0,682,960,720)),(0,682))
    image.paste(restore_patch(leaves,now),PATCH[:2])
    return np.asarray(image)

def main():
    ap=argparse.ArgumentParser(description='One-time legacy HUD migration. Current renders are already clean; do not use in the normal render pipeline.')
    ap.add_argument('--preview',action='store_true')
    ap.add_argument('--output',default='output/D_spacetime_clean.mp4')
    args=ap.parse_args()
    original=ROOT/'output'/'D_spacetime.mp4'
    source=ROOT/'assets'/'bad_apple.mp4'
    output=ROOT/args.output
    if output.resolve()==original.resolve():raise RuntimeError('Refusing to overwrite original')
    outdir=ROOT/'output'/'stills';outdir.mkdir(exist_ok=True,parents=True)
    info=json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-of','json',str(original)],creationflags=CREATE_NO_WINDOW))
    v=next(s for s in info['streams'] if s.get('codec_type')=='video')
    frames=int(v['nb_frames'])
    if args.preview:
        # 51s belongs to the original fixed segment [50,52), plus [52,54).
        offset=50*DATA_FPS
        raw=subprocess.check_output([FFMPEG,'-v','error','-threads','2','-ss','50','-i',str(source),'-t','4','-an','-vf',f'fps={DATA_FPS},scale={W}:{H}:flags=area','-filter_threads','2','-threads','2','-pix_fmt','gray','-f','rawvideo','pipe:1'],creationflags=CREATE_NO_WINDOW)
        vol=np.frombuffer(raw,dtype=np.uint8).reshape(-1,H,W)>128
        leaves=[]
        for start in (0,CHUNK):
            blocks,_=partition(np.moveaxis(vol[start:start+CHUNK],0,2),offset+start)
            leaves.extend(blocks)
        raw=subprocess.check_output([FFMPEG,'-v','error','-threads','2','-ss','51','-i',str(original),'-frames:v','1','-threads','2','-f','rawvideo','-pix_fmt','rgb24','pipe:1'],creationflags=CREATE_NO_WINDOW)
        rgb=np.frombuffer(raw,dtype=np.uint8).reshape(720,960,3)
        image=restyle(rgb,leaves,51*DATA_FPS)
        path=outdir/'D_clean_0051.00.png'
        Image.fromarray(image).save(path)
        print(str(path),flush=True)
        return
    decoder=subprocess.Popen([FFMPEG,'-v','error','-threads','2','-i',str(original),'-an','-threads','2','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
    reader=subprocess.Popen([FFMPEG,'-v','error','-threads','2','-i',str(source),'-an','-vf',f'fps={DATA_FPS},scale={W}:{H}:flags=area','-filter_threads','2','-threads','2','-pix_fmt','gray','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
    encoder=subprocess.Popen([FFMPEG,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','960x720','-r','30','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
    queue=deque();sample_offset=0;ended=False;segments=0
    def get_chunk():
        nonlocal sample_offset,ended,segments
        samples=[]
        for _ in range(CHUNK):
            data=reader.stdout.read(W*H)
            if len(data)<W*H:ended=True;break
            samples.append(np.frombuffer(data,dtype=np.uint8).reshape(H,W)>128)
        if not samples:return
        volume=np.stack(samples,axis=2)
        leaves,_=partition(volume,sample_offset)
        queue.append((sample_offset,sample_offset+len(samples),leaves))
        sample_offset+=len(samples);segments+=1
    started=time.perf_counter();progress_at=0;written=0
    try:
        for frame in range(frames):
            raw=decoder.stdout.read(960*720*3)
            if len(raw)!=960*720*3:raise RuntimeError(f'Early video EOF at {frame}')
            now=frame*DATA_FPS/OUTPUT_FPS
            while not ended and (not queue or queue[-1][1]<now+LOOK):get_chunk()
            while queue and queue[0][1]<=now:queue.popleft()
            leaves=[b for chunk in queue for b in chunk[2]]
            rgb=np.frombuffer(raw,dtype=np.uint8).reshape(720,960,3)
            cleaned=restyle(rgb,leaves,now)
            encoder.stdin.write(cleaned.tobytes());written+=1
            if frame in (51*30,166*30,frames-1):
                Image.fromarray(cleaned).save(outdir/f'D_clean_{frame/30:07.2f}.png')
            elapsed=time.perf_counter()-started
            if elapsed>=progress_at:
                print(f'D clean {written}/{frames}; {elapsed:.1f}s; {written/max(elapsed,.001):.1f} fps',flush=True)
                progress_at=elapsed+15
    finally:
        encoder.stdin.close();encoder.wait()
        decoder.stdout.close();decoder.wait()
        reader.stdout.close();reader.wait()
    if encoder.returncode or decoder.returncode:raise RuntimeError('Video processing failed')
    stats={'original':str(original),'output':str(output),'frames':written,'fps':30,'duration':written/30,'preserved_geometry':'All original decoded image pixels are preserved except a 94x10-pixel far-edge strip restored from the exact original BSP. Empty margins alone are cleared.','edge_patch_xyxy':PATCH,'bsp_segments_validated':segments,'wall_seconds':time.perf_counter()-started,'labels':['x','y','time +2s']}
    output.with_name(output.stem+'_stats.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    print(json.dumps(stats),flush=True)

if __name__=='__main__':main()
