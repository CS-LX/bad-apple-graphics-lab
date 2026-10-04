"""Stream the full-length persistent Delaunay connectivity visualization.

No decoded frames are accumulated. Input is analysed at 480x360; the mesh is
drawn at 960x720. Persistent IDs survive cuts; their positions reset to the
same deterministic rest grid at cuts, with cross-cut trails suppressed.
"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if (ROOT / '.preview-deps').is_dir():
    sys.path.insert(0, str(ROOT / '.preview-deps'))
import argparse
import json
import math
import time
import numpy as np
import cv2
from scipy.spatial import Delaunay, cKDTree
from PIL import Image
from video_common import VideoReader, VideoWriter, probe

cv2.setNumThreads(2)
AW, AH = 480, 360

def sample(a, p):
    return cv2.remap(a, p[:, 0].astype(np.float32).reshape(-1, 1),
                     p[:, 1].astype(np.float32).reshape(-1, 1),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)[:, 0]

class Mesh:
    def __init__(self, fps, width=960, height=720):
        self.dt = 1.0 / fps
        self.fps = fps
        self.width, self.height = width, height
        self.scale = np.array([width/AW, height/AH], dtype=np.float32)
        rng = np.random.default_rng(1949)
        x, y = np.meshgrid(np.linspace(2, AW-3, 48), np.linspace(2, AH-3, 36))
        self.origin = np.column_stack((x.ravel(), y.ravel())).astype(np.float32)
        self.origin += rng.uniform(-2, 2, self.origin.shape).astype(np.float32)
        self.origin[:, 0] = self.origin[:, 0].clip(1, AW-2)
        self.origin[:, 1] = self.origin[:, 1].clip(1, AH-2)
        bx, by = np.linspace(0, AW-1, 49), np.linspace(0, AH-1, 37)
        border = np.vstack((np.column_stack((bx,bx*0)),
            np.column_stack((bx,bx*0+AH-1)),np.column_stack((by*0,by)),
            np.column_stack((by*0+AW-1,by)))).astype(np.float32)
        self.pts = np.vstack((self.origin,np.unique(border,axis=0)))
        self.n_mobile = len(self.origin)
        self.last_gray = None
        self.last_edges = set()
        self.birth = {}
        self.dead = []
        self.tri = None
        self.cut_count = 0
        self.flow_frames = 0
        self.new_count = 0
        self.removed_count = 0
        self.peak_changed = 0
        self.trail_seconds = .25

    def advance(self, gray):
        old = self.pts.copy()
        cut = False
        if self.last_gray is not None:
            a, b = self.last_gray[::4,::4], gray[::4,::4]
            dif = cv2.absdiff(a,b)
            mean_diff = float(dif.mean()) / 255
            cut = mean_diff > .38 and float(np.mean(dif > 96)) > .55
            if cut:
                self.pts[:self.n_mobile] = self.origin
                self.birth.clear()
                self.dead.clear()
                self.last_edges.clear()
                self.cut_count += 1
            else:
                moving = self.pts[:self.n_mobile]
                # Optical flow is indeterminate on blank frames. Skip there.
                if mean_diff > .00005 and float(gray.std()) > 2.0:
                    flow = cv2.calcOpticalFlowFarneback(self.last_gray, gray, None,
                                                      .5, 4, 25, 4, 7, 1.5, 0)
                    motion = np.column_stack((sample(flow[:,:,0],moving),
                                               sample(flow[:,:,1],moving)))
                    norm = np.linalg.norm(motion,axis=1)
                    motion *= np.minimum(1,108*self.dt/np.maximum(norm,1e-6))[:,None]
                    moving += .65*motion
                    self.flow_frames += 1
                moving += (1-math.exp(-.42*self.dt)) * (self.origin-moving)
                # Bound excursion, including when abrupt transitions escape
                # the intentionally conservative hard-cut detector.
                off = moving-self.origin
                length = np.linalg.norm(off,axis=1)
                moving[:] = self.origin + off*np.minimum(1,44/np.maximum(length,1e-6))[:,None]
                strength = 1-math.exp(-3.6*self.dt)
                for _ in range(2):
                    pairs = cKDTree(moving).query_pairs(4.4,output_type='ndarray')
                    if len(pairs):
                        d=moving[pairs[:,0]]-moving[pairs[:,1]]
                        length=np.maximum(np.linalg.norm(d,axis=1),.01)
                        push=d/length[:,None]*(4.4-length)[:,None]*strength
                        rep=np.zeros_like(moving)
                        np.add.at(rep,pairs[:,0],push)
                        np.add.at(rep,pairs[:,1],-push)
                        moving+=rep
                moving[:,0]=moving[:,0].clip(1,AW-2)
                moving[:,1]=moving[:,1].clip(1,AH-2)

        changed = self.tri is None or np.max(np.abs(old-self.pts)) > .0001
        if changed:
            self.tri = Delaunay(self.pts).simplices
        tri = self.tri
        edge_array=np.sort(np.concatenate((tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]])),axis=1)
        edge_array=np.unique(edge_array,axis=0)
        edges=set(map(tuple,edge_array.tolist()))
        added=edges-self.last_edges if self.last_edges else set()
        removed=self.last_edges-edges
        self.birth={e:age+self.dt for e,age in self.birth.items()
                    if age+self.dt<self.trail_seconds and e in edges}
        self.birth.update({e:0.0 for e in added})
        self.dead=[(a,b,age+self.dt) for a,b,age in self.dead
                   if age+self.dt<self.trail_seconds]
        self.dead.extend((old[a].copy(),old[b].copy(),0.0) for a,b in removed)
        self.last_edges=edges
        self.last_gray=gray
        self.new_count+=len(added)
        self.removed_count+=len(removed)
        self.peak_changed=max(self.peak_changed,len(added))
        return self.render(gray,edge_array),len(added),len(removed),cut

    def render(self,gray,edges):
        canvas=np.empty((self.height,self.width,3),np.uint8)
        canvas[:]=(3,7,13)
        pixels=np.rint(self.pts*self.scale).astype(np.int32)
        tri_pixels=pixels[self.tri]
        values=sample(gray,self.pts[self.tri].mean(axis=1))/255.0
        # Only polygon brightness is quantized for batch rasterization.
        bins=np.rint(values*15).astype(np.uint8)
        for q in range(1,16):
            group=tri_pixels[bins==q]
            if len(group):
                color=tuple(int(a+(q/15)*b) for a,b in zip((3,7,13),(29,52,64)))
                cv2.fillPoly(canvas,group,color,lineType=cv2.LINE_8)
        edge_values=sample(gray,self.pts[edges].mean(axis=1))/255.0
        edge_bins=np.rint(edge_values*15).astype(np.uint8)
        edge_pixels=pixels[edges]
        for q in range(16):
            group=edge_pixels[edge_bins==q]
            if len(group):
                color=tuple(int(a+(q/15)*b) for a,b in zip((8,18,27),(69,99,112)))
                cv2.polylines(canvas,group,False,color,1,cv2.LINE_AA)
        glow=np.zeros_like(canvas)
        accent=np.zeros_like(canvas)
        # Age batches keep rendering cost independent of the edge count.
        fade_levels=max(1,int(math.ceil(self.trail_seconds*self.fps)))
        dead_groups={}
        if self.dead:
            endpoints=np.asarray([(a,b) for a,b,age in self.dead],dtype=np.float32)
            coords=np.rint(endpoints*self.scale).astype(np.int32)
            ages=np.rint(np.asarray([age for a,b,age in self.dead])*self.fps).astype(np.int32)
            dead_groups={q:coords[ages==q] for q in np.unique(ages)}
        born_groups={}
        if self.birth:
            edge_ids=np.asarray(list(self.birth),dtype=np.int32)
            coords=pixels[edge_ids]
            ages=np.rint(np.fromiter(self.birth.values(),dtype=np.float64)*self.fps).astype(np.int32)
            born_groups={q:coords[ages==q] for q in np.unique(ages)}
        for groups,core,halo in ((dead_groups,(255,141,70),(255,126,51)),
                                  (born_groups,(56,225,255),(36,215,255))):
            # Render older edges first so fresh edges dominate crossings.
            for q in sorted(groups,reverse=True):
                alpha=max(0,1-(q/self.fps)/self.trail_seconds)
                group=np.asarray(groups[q],dtype=np.int32)
                cv2.polylines(glow,group,False,tuple(int(c*alpha*.5) for c in halo),5,cv2.LINE_AA)
                cv2.polylines(accent,group,False,tuple(int(c*alpha) for c in core),2,cv2.LINE_AA)
        # Add the fading light to the base. Directly painting a darkened color
        # would turn old trails into black crosses on bright silhouettes.
        canvas=cv2.add(canvas,cv2.add(accent,cv2.GaussianBlur(glow,(0,0),2.6)))
        vv=sample(gray,self.pts)
        for q in pixels[vv>127]:
            cv2.circle(canvas,tuple(q),1,(140,184,194),-1,cv2.LINE_AA)
        return canvas

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'assets'/'bad_apple.mp4')
    parser.add_argument('--output',type=Path,default=ROOT/'output'/'C_mesh.mp4')
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float,default=None)
    parser.add_argument('--fps',type=float,default=30)
    parser.add_argument('--width',type=int,default=960)
    parser.add_argument('--height',type=int,default=720)
    parser.add_argument('--tag',default='C_mesh')
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    stilldir=args.output.parent/'stills'
    stilldir.mkdir(exist_ok=True)
    stats_path=args.output.parent/f'{args.tag}_stats.json'
    progress_path=args.output.parent/f'{args.tag}_progress.json'
    source_info=probe(args.source)
    video_info=next(s for s in source_info['streams'] if s.get('codec_type')=='video')
    # Container duration includes an audio tail; the reader stops at video EOF.
    total_duration=float(video_info.get('duration',source_info['format']['duration']))
    duration=min(args.duration,total_duration-args.start) if args.duration is not None else total_duration-args.start
    expected=int(math.ceil(duration*args.fps-1e-4))
    reader=VideoReader(args.source,AW,AH,args.fps,start=args.start,duration=args.duration)
    writer=VideoWriter(args.output,args.width,args.height,args.fps,threads=2)
    mesh=Mesh(args.fps,args.width,args.height)
    chosen=[30,51,90,125,165,200,217]
    if args.duration is not None:
        chosen=[args.start+args.duration*.5,args.start+args.duration*.85]
    still_frames={int(round((t-args.start)*args.fps)):t for t in chosen if args.start<=t<args.start+duration}
    started=time.perf_counter()
    frame_count=0
    changed_per_second=[]
    count_this_second=0
    for idx,gray in enumerate(reader):
        rgb,added,removed,cut=mesh.advance(gray)
        writer.write(rgb)
        frame_count=idx+1
        count_this_second+=added
        if frame_count%round(args.fps)==0:
            changed_per_second.append(count_this_second)
            count_this_second=0
        if idx in still_frames:
            stamp=still_frames[idx]
            Image.fromarray(rgb).save(stilldir/f'{args.tag}_{stamp:07.3f}.png')
        if frame_count%150==0:
            elapsed=time.perf_counter()-started
            info={'frames':frame_count,'expected_frames':expected,'elapsed_seconds':round(elapsed,2),
                  'render_fps':round(frame_count/elapsed,3),'source_seconds':round(args.start+frame_count/args.fps,3),
                  'cut_resets':mesh.cut_count,'eta_seconds':round((expected-frame_count)/(frame_count/elapsed),1)}
            progress_path.write_text(json.dumps(info,indent=2),encoding='utf-8')
            print(json.dumps(info),flush=True)
    writer.close()
    elapsed=time.perf_counter()-started
    stats={'algorithm':'Persistent Delaunay connectivity changes',
        'source':str(args.source),'output':str(args.output),'frames':frame_count,
        'fps':args.fps,'width':args.width,'height':args.height,'start_seconds':args.start,
        'source_duration_seconds':duration,'output_duration_seconds':frame_count/args.fps,
        'wall_seconds':elapsed,'render_fps':frame_count/elapsed,'vertices':len(mesh.pts),
        'optical_flow_frames':mesh.flow_frames,'cut_resets':mesh.cut_count,
        'total_added_edges':mesh.new_count,'total_removed_edges':mesh.removed_count,
        'peak_added_in_one_frame':mesh.peak_changed,'added_edges_per_second':changed_per_second,
        'trail_seconds':mesh.trail_seconds,'analysis_size':[AW,AH],
        'limitations':[
            'Connectivity differences between time steps, not isolated elementary edge flips.',
            'Low-brightness triangle fills and base-edge brightness also sample the source image.',
            'Flow advection is approximate in untextured silhouettes, stabilized by rest-grid springs, repulsion and bounded excursion.',
            'On detected hard cuts, persistent vertex IDs reset to their same original grid positions; cross-cut edge trails are cleared.',
            'No audio in this intermediate; original soundtrack is muxed by the final assembly step.'
        ],'status':'complete'}
    stats_path.write_text(json.dumps(stats,indent=2),encoding='utf-8')
    progress_path.write_text(json.dumps(stats,indent=2),encoding='utf-8')
    print(json.dumps({k:stats[k] for k in ['status','frames','wall_seconds','render_fps','output']}),flush=True)

if __name__=='__main__':
    main()
