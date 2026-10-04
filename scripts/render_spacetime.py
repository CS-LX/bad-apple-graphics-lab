"""Render the full source as exact space-time BSP blocks, 15 Hz data / 30 Hz scan.

Input samples are binarized at 120x90, split in fixed two-second chunks. A rolling
two-second view crosses chunk boundaries continuously. Each box is a genuine
homogeneous BSP leaf. No source-shaped decorative boxes are introduced.
"""
from pathlib import Path
import argparse, json, math, subprocess, sys, time
from collections import deque
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from video_common import FFMPEG, FFPROBE, CREATE_NO_WINDOW, find_font

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.preview-deps'))
import cv2
cv2.setNumThreads(2)

W,H=120,90
DATA_FPS,OUTPUT_FPS=15,30
CHUNK=30
LOOK=30
SX,SY,DX,DY=5.55,5.55,6.16,-2.4
OX,OY=48,176

def partition(volume,offset):
    leaves=[]
    nodes=0
    def rec(box):
        nonlocal nodes
        nodes+=1
        y0,y1,x0,x1,t0,t1=box
        v=volume[y0:y1,x0:x1,t0:t1]
        n,k=v.size,int(v.sum())
        if k==0:return
        if k==n:
            leaves.append((x0,x1,y0,y1,t0+offset,t1+offset))
            return
        best=None
        base=k-k*k/n
        for axis in range(3):
            size=v.shape[axis]
            if size<2:continue
            sums=v.sum(axis=tuple(a for a in range(3) if a!=axis)).astype(float)
            lk=np.cumsum(sums)[:-1]
            ln=np.arange(1,size)*n/size
            rk,rn=k-lk,n-ln
            gains=base-(lk-lk*lk/ln+rk-rk*rk/rn)
            idx=int(np.argmax(gains))
            cand=(float(gains[idx]),-abs(idx+1-size/2)/size,axis,idx+1)
            if best is None or cand>best:best=cand
        _,_,axis,cut=best
        a,b=list(box),list(box)
        where=box[axis*2]+cut
        a[axis*2+1]=where;b[axis*2]=where
        rec(tuple(a));rec(tuple(b))
    rec((0,volume.shape[0],0,volume.shape[1],0,volume.shape[2]))
    # Validate every segment from the actual emitted boxes.
    reconstruction=np.zeros_like(volume)
    for x0,x1,y0,y1,t0,t1 in leaves:
        reconstruction[y0:y1,x0:x1,t0-offset:t1-offset]=True
    error=int(np.count_nonzero(reconstruction!=volume))
    if error:raise RuntimeError(f'BSP reconstruction error: {error}')
    return leaves,nodes

def color(length):
    a=min(1.0,(length-1)/14)
    if a<.5:
        f=a*2;lo=(30,158,205);hi=(105,214,204)
    else:
        f=(a-.5)*2;lo=(105,214,204);hi=(250,183,75)
    c=tuple(int(lo[i]*(1-f)+hi[i]*f) for i in range(3))
    return c

def tint(c,v):return tuple(min(255,int(x*v)) for x in c)
COLORS={n:(color(n),tint(color(n),.55),tint(color(n),.36),tint(color(n),.34)) for n in range(1,CHUNK+1)}

def font(size):
    font_path=find_font()
    return ImageFont.truetype(str(font_path),size) if font_path else ImageFont.load_default()
F_AXIS=font(14)

def point(x,y,t):return (round(OX+x*SX+t*DX),round(OY+y*SY+t*DY))

def background():
    image=Image.new('RGB',(960,720),(6,12,22))
    d=ImageDraw.Draw(image)
    # Compact orientation triad in the otherwise empty margin. Its directions
    # match the actual image x/y axes and the projected temporal extrusion.
    axis_color=(134,171,191)
    origin=(54,59)
    d.line([origin,(126,59)],fill=axis_color,width=1)
    d.line([(121,56),(126,59),(121,62)],fill=axis_color,width=1)
    d.text((132,48),'x',font=F_AXIS,fill=axis_color)
    d.line([origin,(54,90)],fill=axis_color,width=1)
    d.line([(51,85),(54,90),(57,85)],fill=axis_color,width=1)
    d.text((62,76),'y',font=F_AXIS,fill=axis_color)
    d.line([origin,(116,35)],fill=axis_color,width=1)
    d.line([(110,34),(116,35),(112,40)],fill=axis_color,width=1)
    d.text((123,22),'time +2s',font=F_AXIS,fill=axis_color)
    for t in (0,LOOK):
        for y in (0,H):d.line([point(0,y,t),point(W,y,t)],fill=(19,36,49))
        for x in (0,W):d.line([point(x,0,t),point(x,H,t)],fill=(19,36,49))
    for x in (0,W):
        for y in (0,H):d.line([point(x,y,0),point(x,y,LOOK)],fill=(29,56,70))
    return image
BASE=background()

def render(leaves,now,current,second):
    image=BASE.copy();d=ImageDraw.Draw(image)
    end=now+LOOK
    candidates=[]
    fronts=[]
    for b in leaves:
        x0,x1,y0,y1,t0,t1=b
        if t1<=now or t0>=end:continue
        duration=t1-t0
        a=max(t0,now)-now;z=min(t1,end)-now
        candidates.append(((a+z)*.5-.28*(x0+x1)*.5+.1*(y0+y1)*.5,(x0,x1,y0,y1,a,z,duration)))
    candidates.sort(key=lambda v:v[0],reverse=True)
    for _,b in candidates:
        x0,x1,y0,y1,a,z,duration=b
        c,top,side,edge=COLORS[duration]
        a00=point(x0,y0,a);a10=point(x1,y0,a)
        a11=point(x1,y1,a);a01=point(x0,y1,a)
        z00=point(x0,y0,z);z10=point(x1,y0,z);z11=point(x1,y1,z)
        d.polygon((a00,a10,z10,z00),fill=top,outline=edge)
        d.polygon((a10,a11,z11,z10),fill=side,outline=edge)
        d.polygon((a00,a10,a11,a01),fill=c,outline=edge)
        if a==0:fronts.append(((a00,a10,a11,a01),c,edge))
    # Re-emphasize the exact near slice; the source can always be read clearly.
    for pts,c,edge in fronts:d.polygon(pts,fill=c,outline=edge)
    contours,_=cv2.findContours(current,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        pts=[point(float(q[0][0])+.5,float(q[0][1])+.5,0) for q in contour]
        if len(pts)>2:d.line(pts+[pts[0]],fill=(207,245,238),width=1)
    return np.asarray(image)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float,default=None)
    parser.add_argument('--output',default='output/D_spacetime.mp4')
    args=parser.parse_args()
    source=ROOT/'assets'/'bad_apple.mp4'
    info=json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_format','-show_streams','-of','json',str(source)],creationflags=CREATE_NO_WINDOW))
    video_stream=next(s for s in info['streams'] if s.get('codec_type')=='video')
    source_frames=int(video_stream.get('nb_frames',0))
    total=source_frames/OUTPUT_FPS if source_frames else float(video_stream.get('duration',info['format']['duration']))
    duration=min(args.duration if args.duration is not None else total-args.start,total-args.start)
    output=ROOT/args.output;output.parent.mkdir(exist_ok=True,parents=True)
    (ROOT/'output'/'stills').mkdir(exist_ok=True,parents=True)
    read_duration=min(duration+LOOK/DATA_FPS,total-args.start)
    reader=subprocess.Popen([FFMPEG,'-v','error','-threads','2','-ss',str(args.start),'-i',str(source),'-t',str(read_duration),'-an','-vf',f'fps={DATA_FPS},scale={W}:{H}:flags=area','-threads','2','-filter_threads','2','-pix_fmt','gray','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
    encoder=subprocess.Popen([FFMPEG,'-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','960x720','-r',str(OUTPUT_FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
    queue=deque();sample_offset=0;ended=False;segment_stats=[]
    def get_chunk():
        nonlocal sample_offset,ended
        samples=[]
        for _ in range(CHUNK):
            data=reader.stdout.read(W*H)
            if len(data)<W*H:
                ended=True;break
            samples.append(np.frombuffer(data,dtype=np.uint8).reshape(H,W)>128)
        if not samples:return
        volume=np.stack(samples,axis=2)
        before=time.perf_counter()
        leaves,nodes=partition(volume,sample_offset)
        segment_stats.append({'first_sample':sample_offset,'samples':len(samples),'white_leaves':len(leaves),'nodes':nodes,'partition_seconds':round(time.perf_counter()-before,3),'reconstruction_error':0})
        queue.append((sample_offset,sample_offset+len(samples),volume,leaves))
        sample_offset+=len(samples)
    frames=int(round(duration*OUTPUT_FPS))
    started=time.perf_counter()
    progress_at=0
    captures={0,round(1.2*OUTPUT_FPS),round(3*OUTPUT_FPS),round(51*OUTPUT_FPS),round(107*OUTPUT_FPS),round(166*OUTPUT_FPS),frames-1}
    last_current=np.zeros((H,W),dtype=np.uint8)
    written=0
    try:
        for frame in range(frames):
            now=frame*DATA_FPS/OUTPUT_FPS
            while not ended and (not queue or queue[-1][1]<now+LOOK):get_chunk()
            while queue and queue[0][1]<=now:queue.popleft()
            all_leaves=[b for chunk in queue for b in chunk[3]]
            if queue:
                first,end,volume,_=queue[0]
                index=min(volume.shape[2]-1,max(0,int(math.floor(now))-first))
                last_current=volume[:,:,index].astype(np.uint8)
            rgb=render(all_leaves,now,last_current,args.start+frame/OUTPUT_FPS)
            encoder.stdin.write(rgb.tobytes());written+=1
            if frame in captures:
                Image.fromarray(rgb).save(ROOT/'output'/'stills'/f'D_{args.start+frame/OUTPUT_FPS:07.2f}.png')
            elapsed=time.perf_counter()-started
            if elapsed>=progress_at:
                print(f'D BSP {frame+1}/{frames}, elapsed={elapsed:.1f}s, render_fps={(frame+1)/max(elapsed,.001):.1f}, segments={len(segment_stats)}',flush=True)
                progress_at=elapsed+15
    finally:
        encoder.stdin.close()
        encoder.wait()
        reader.stdout.close()
        reader.wait()
    if encoder.returncode:raise RuntimeError(f'Encoder exit {encoder.returncode}')
    stats={'source':str(source),'output':str(output),'start':args.start,'duration':duration,'output_frames':written,'output_fps':OUTPUT_FPS,'data_fps':DATA_FPS,'sample_shape':[H,W],'chunk_frames':CHUNK,'lookahead_frames':LOOK,'wall_seconds':round(time.perf_counter()-started,3),'reconstruction_error_voxels':0,'method':'Exact homogeneous-leaf BSP, exhaustive Gini gain splits. Fixed disjoint 2-second partitions rendered through a continuous rolling 2-second temporal window. Binary input at 15fps; fractional geometry scan and output at 30fps. Black leaves omitted.','segments':segment_stats}
    stats_path=output.with_name(output.stem+'_stats.json')
    stats_path.write_text(json.dumps(stats,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in stats.items() if k!='segments'}),flush=True)

if __name__=='__main__':main()
