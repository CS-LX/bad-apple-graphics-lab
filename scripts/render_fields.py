"""Full-length A (tree events) / B (signed-distance time derivative)."""
from pathlib import Path
import argparse, json, time, math
from collections import deque
from video_common import ROOT, VideoReader, VideoWriter
import numpy as np
import cv2
from scipy.ndimage import distance_transform_edt, gaussian_filter

cv2.setNumThreads(2)
BG=np.array([6,11,20],np.float32)
CYAN=np.array([66,231,255],np.float32)
ORANGE=np.array([255,121,65],np.float32)

class TreeEvents:
    def __init__(self,fps,width,height):
        self.fps,self.width,self.height=fps,width,height
        self.previous=set();self.history=deque();self.events=[]
        self.work=np.zeros((512,512),np.uint8)
    def splits(self,gray):
        self.work[64:448,:]=(cv2.resize(gray,(512,384),interpolation=cv2.INTER_AREA)>127)
        integral=cv2.integral(self.work,sdepth=cv2.CV_32S)
        nodes=set()
        def visit(x,y,s):
            n=int(integral[y+s,x+s]-integral[y,x+s]-integral[y+s,x]+integral[y,x])
            if s<=4 or n<.018*s*s or n>.982*s*s:return
            nodes.add((x,y,s));h=s//2
            visit(x,y,h);visit(x+h,y,h);visit(x,y+h,h);visit(x+h,y+h,h)
        visit(0,0,512)
        return nodes
    def render(self,gray,index):
        current=self.splits(gray)
        born=current-self.previous;died=self.previous-current
        # No event in the first frame: there is no previous frame to compare.
        if index==0:born=set();died=set()
        self.history.append((index,born,died))
        while self.history and (index-self.history[0][0])/self.fps>.5:self.history.popleft()
        layer=np.zeros((768,1024,3),np.uint8)
        for at,births,deaths in self.history:
            fade=math.exp(-(index-at)/self.fps/.233)
            for nodes,color in ((deaths,ORANGE),(births,CYAN)):
                col=tuple(int(v*fade) for v in color)
                outline=tuple(int(v*.38) for v in col)
                # Coarse nodes first, fine nodes on top, matching the preview.
                for x,y,s in sorted(nodes,key=lambda n:-n[2]):
                    x*=2;y=y*2-128;s*=2;h=s//2
                    cv2.rectangle(layer,(x+1,y+1),(x+s-1,y+s-1),outline,1)
                    cv2.line(layer,(x+h,y),(x+h,y+s),col,2)
                    cv2.line(layer,(x,y+h),(x+s,y+h),col,2)
                    if s>=24:
                        for ox,oy in ((s//4,s//4),(3*s//4,s//4),(s//4,3*s//4),(3*s//4,3*s//4)):
                            cv2.circle(layer,(x+ox,y+oy),1,col,-1)
        glow=cv2.GaussianBlur(layer,(0,0),4)
        rgb=np.clip(layer.astype(np.uint16)+glow.astype(np.uint16)+BG.astype(np.uint16),0,255).astype(np.uint8)
        rgb=cv2.resize(rgb,(self.width,self.height),interpolation=cv2.INTER_AREA)
        self.events.append({'frame':index,'split':len(born),'merge':len(died),'nodes':len(current)})
        self.previous=current
        return rgb

def signed_field(gray):
    m=gray>127
    if not m.any() or m.all():return None
    return gaussian_filter(distance_transform_edt(~m)-distance_transform_edt(m),.65).astype(np.float32)

def render_sdf(phi,prev,nxt,fps,width,height):
    if phi is None:return np.full((height,width,3),BG,dtype=np.uint8)
    if prev is None and nxt is None:velocity=np.zeros_like(phi)
    elif prev is None:velocity=(nxt-phi)*fps
    elif nxt is None:velocity=(phi-prev)*fps
    else:velocity=(nxt-prev)*(fps/2)
    v=np.sign(velocity)*np.abs(np.tanh(velocity/18))**.7
    col=np.maximum(v,0)[...,None]*ORANGE+np.maximum(-v,0)[...,None]*CYAN
    dist=np.abs((phi+4.5)%9-4.5)
    bands=np.exp(-(dist/.75)**2)
    edge=np.exp(-(phi/1.25)**2)
    rgb=BG+col*(.16+.84*bands)[...,None]
    rgb+=edge[...,None]*np.array([125,141,156],np.float32)*.7
    glow=cv2.GaussianBlur(col*bands[...,None]*.2,(0,0),2)
    rgb=np.clip(rgb+glow,0,255).astype(np.uint8)
    return cv2.resize(rgb,(width,height),interpolation=cv2.INTER_CUBIC)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['tree','sdf'])
    p.add_argument('--source',type=Path,default=ROOT/'assets/bad_apple.mp4')
    p.add_argument('--output',type=Path)
    p.add_argument('--start',type=float,default=0)
    p.add_argument('--duration',type=float)
    p.add_argument('--fps',type=float,default=30)
    p.add_argument('--width',type=int,default=960);p.add_argument('--height',type=int,default=720)
    args=p.parse_args()
    name='A_tree' if args.mode=='tree' else 'B_sdf'
    output=args.output or ROOT/'output'/f'{name}.mp4'
    output.parent.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    reader=VideoReader(args.source,480,360,args.fps,args.start,args.duration)
    writer=VideoWriter(output,args.width,args.height,args.fps)
    stills=ROOT/'output/stills';stills.mkdir(parents=True,exist_ok=True)
    count=0;blank=0
    checkpoint={round(s*args.fps) for s in (3,25,51,90,130,170,210)}
    def write(rgb):
        nonlocal count
        writer.write(rgb)
        source_seconds=args.start+count/args.fps
        if count in checkpoint or (args.duration is not None and count==round(3*args.fps)):
            cv2.imwrite(str(stills/f'{output.stem}_{source_seconds:06.2f}.png'),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        count+=1
        if count%150==0:
            elapsed=time.perf_counter()-start
            state={'mode':args.mode,'frames':count,'source_seconds':source_seconds,'wall_seconds':round(elapsed,2),'render_fps':round(count/elapsed,2)}
            output.with_suffix('.progress.json').write_text(json.dumps(state),encoding='utf8')
            print(json.dumps(state),flush=True)
    try:
        if args.mode=='tree':
            renderer=TreeEvents(args.fps,args.width,args.height)
            for i,gray in enumerate(reader):write(renderer.render(gray,i))
        else:
            previous=None
            current=signed_field(next(reader))
            for gray in reader:
                upcoming=signed_field(gray)
                if current is None:blank+=1
                write(render_sdf(current,previous,upcoming,args.fps,args.width,args.height))
                previous,current=current,upcoming
            if current is None:blank+=1
            write(render_sdf(current,previous,None,args.fps,args.width,args.height))
    finally:
        reader.close();writer.close()
    stats={'mode':args.mode,'frames':count,'fps':args.fps,'duration':count/args.fps,'width':args.width,'height':args.height,'elapsed_seconds':time.perf_counter()-start,'source_start':args.start,'audio':'Silent intermediate; original audio muxed after verification.'}
    if args.mode=='tree':
        stats.update({'algorithm':'Difference of internal quadtree node sets at fixed image coordinates; split cyan, merge orange. 0.5-second decaying event trail.','events':renderer.events,'minimum_cell':4,'mixed_threshold':.018})
    else:
        stats.update({'algorithm':'Euclidean signed distance to thresholded contour; central time derivative. Positive orange, negative cyan; contours every 9 source pixels.','uniform_frames':blank,'uniform_handling':'No contour exists in a uniform frame: render blank. At adjacent valid frames use one-sided differences.','limitations':'Temporal SDF differences are not physical pressure or a simulated propagating wave.'})
    output.with_suffix('.stats.json').write_text(json.dumps(stats,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in stats.items() if k!='events'}),flush=True)

if __name__=='__main__':main()
