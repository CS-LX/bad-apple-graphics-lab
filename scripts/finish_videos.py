"""Build presentation-ready videos, static warnings, and a local viewing gallery."""
from pathlib import Path
import argparse, concurrent.futures, json, subprocess
from video_common import ROOT, FFMPEG, CREATE_NO_WINDOW, probe
from presentation import WARNING_SECONDS, save_warning

OUT=ROOT/'output'; DEST=ROOT/'deliverables'; SOURCE=ROOT/'assets/bad_apple.mp4'
FPS=30; SOURCE_FRAMES=6572
ITEMS=[
 ('A_tree.mp4','A_quadtree_events.mp4','A · 四叉树结构差分','QUADTREE EVENTS','相邻帧四叉树内部节点集合的增删；青色分裂，橙色合并，余辉0.5秒。采用512×512黑边填充域、4像素最小叶块和1.8%混色阈值。'),
 ('B_sdf.mp4','B_sdf_time_derivative.mp4','B · 距离场的时间导数','SDF TIME DERIVATIVE','平滑的离散有符号距离场做时间差分；青色减小，橙色增大。白线是当前轮廓，彩线是等距线；纯色帧无轮廓时显示暗背景。'),
 ('C_mesh.mp4','C_delaunay_connectivity.mp4','C · 持续三角网格连边变化','DELAUNAY CONNECTIVITY','固定ID采样点受光流推动并稳定化；青色新增边、橙色删除边。淡色三角面保留原帧亮度。展示采样时刻的连边集合变化，并非逐个基础边翻转。'),
 ('D_spacetime.mp4','D_spacetime_bsp.mp4','D · 时空 BSP','SPACETIME BSP','120×90×时间的二值数据以15fps采样，30fps连续几何扫描。对固定2秒数据段做真实BSP；青色块时间跨度短，金色块在该段内持续至少1秒，并非跨整片追踪的区域寿命。画面只保留空间与时间轴说明。'),
]

def run(cmd):
    subprocess.run(cmd,cwd=ROOT,check=True,creationflags=CREATE_NO_WINDOW)

def check_video(path,frames=SOURCE_FRAMES,size=(960,720),audio=True):
    info=probe(path);v=next(s for s in info['streams'] if s['codec_type']=='video')
    assert (v['width'],v['height'])==size,(path,'dimensions')
    assert v['r_frame_rate']=='30/1',(path,'fps')
    assert int(v['nb_frames'])==frames,(path,'frames',v.get('nb_frames'))
    assert abs(float(v['duration'])-frames/FPS)<.04,(path,'duration')
    a=[s for s in info['streams'] if s['codec_type']=='audio']
    if audio:assert len(a)==1 and a[0]['codec_name']=='aac',(path,'audio')
    return {'file':path.name,'frames':frames,'fps':FPS,'width':size[0],'height':size[1],
            'video_duration':float(v['duration']),'audio_duration':float(a[0]['duration']) if a else None,
            'bytes':path.stat().st_size}

def completed(path,frames,size=(960,720)):
    if not path.is_file():return False
    try:check_video(path,frames,size);return True
    except (AssertionError,subprocess.CalledProcessError,KeyError,ValueError):return False

def prepend_warning(body,target,size=(960,720),duration=SOURCE_FRAMES/FPS,
                    audio_source=SOURCE,audio_start=0,body_start=0,card=None):
    """Render five silent seconds, then begin picture and soundtrack together."""
    frames=round(duration*FPS)+WARNING_SECONDS*FPS
    card=card or save_warning(size)
    temp=target.with_name(target.stem+'.pending.mp4')
    cmd=[FFMPEG,'-hide_banner','-loglevel','error','-y','-filter_complex_threads','1',
         '-threads','2','-ss',str(body_start),'-i',str(body),
         '-loop','1','-framerate',str(FPS),'-i',str(card),
         '-threads','1','-ss',str(audio_start),'-i',str(audio_source)]
    filt=(f'[1:v]trim=duration={WARNING_SECONDS},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[w];'
          f'[0:v]trim=duration={duration},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[b];'
          '[w][b]concat=n=2:v=1:a=0[v];'
          f'[2:a]atrim=duration={duration},asetpts=PTS-STARTPTS,adelay={WARNING_SECONDS*1000}:all=1[a]')
    cmd+=['-filter_complex',filt,'-map','[v]','-map','[a]',
          '-c:v','libx264','-preset','fast','-crf','18','-threads','3','-pix_fmt','yuv420p',
          '-c:a','aac','-b:a','192k','-ar','44100','-frames:v',str(frames),
          '-t',str(frames/FPS),'-movflags','+faststart',str(temp)]
    run(cmd);check_video(temp,frames,size);temp.replace(target)

def mux_one(index,force=False,card=None):
    src,name,title,_,_=ITEMS[index]
    source=OUT/src;target=DEST/name
    frames=SOURCE_FRAMES+(WARNING_SECONDS*FPS if index<3 else 0)
    if not force and completed(target,frames) and (not source.exists() or target.stat().st_mtime>=source.stat().st_mtime):
        return check_video(target,frames)
    check_video(source,audio=False)
    if index<3:prepend_warning(source,target,card=card)
    else:
        temp=target.with_name(target.stem+'.pending.mp4')
        run([FFMPEG,'-hide_banner','-loglevel','error','-y','-i',str(source),'-i',str(SOURCE),
             '-map','0:v:0','-map','1:a:0','-c','copy','-t',str(SOURCE_FRAMES/FPS),
             '-movflags','+faststart','-metadata',f'title={title}',str(temp)])
        check_video(temp);temp.replace(target)
    print(f'Complete: {name}',flush=True)
    return check_video(target,frames)

def mux(only=None,force=False):
    DEST.mkdir(exist_ok=True);OUT.mkdir(exist_ok=True)
    indices=[i for i in range(4) if only is None or chr(65+i) in only]
    card=save_warning()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda i:mux_one(i,force,card),indices))
    all_results=[]
    for i,(_,name,_,_,_) in enumerate(ITEMS):
        frames=SOURCE_FRAMES+(WARNING_SECONDS*FPS if i<3 else 0)
        if completed(DEST/name,frames):all_results.append(check_video(DEST/name,frames))
    (DEST/'validation.json').write_text(json.dumps(all_results,ensure_ascii=False,indent=2),encoding='utf8')
    return results

def comparison(force=False):
    target=DEST/'00_four_way_comparison.mp4';total=SOURCE_FRAMES+WARNING_SECONDS*FPS
    stale=force or not completed(target,total,(1280,960)) or any((DEST/name).stat().st_mtime>target.stat().st_mtime for _,name,_,_,_ in ITEMS)
    if stale:
        cmd=[FFMPEG,'-hide_banner','-loglevel','error','-y','-filter_complex_threads','2']
        for i,(_,name,_,_,_) in enumerate(ITEMS):
            cmd+=['-threads','2','-ss',str(WARNING_SECONDS if i<3 else 0),'-i',str(DEST/name)]
        card=save_warning((1280,960))
        cmd+=['-loop','1','-framerate','30','-i',str(card),'-threads','1','-i',str(SOURCE)]
        filters=[f'[{i}:v]setpts=PTS-STARTPTS,scale=640:480:flags=lanczos,setsar=1[v{i}]' for i in range(4)]
        filters+=['[v0][v1][v2][v3]xstack=inputs=4:layout=0_0|640_0|0_480|640_480:fill=0x060B14[grid]',
                  f'[4:v]trim=duration={WARNING_SECONDS},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[w]',
                  '[w][grid]concat=n=2:v=1:a=0[v]',
                  f'[5:a]atrim=duration={SOURCE_FRAMES/FPS},asetpts=PTS-STARTPTS,adelay={WARNING_SECONDS*1000}:all=1[a]']
        temp=target.with_name(target.stem+'.pending.mp4')
        cmd+=['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]',
              '-c:v','libx264','-preset','fast','-crf','19','-threads','4','-c:a','aac','-b:a','192k',
              '-frames:v',str(total),'-t',str(total/FPS),'-pix_fmt','yuv420p','-movflags','+faststart',str(temp)]
        run(cmd);check_video(temp,total,(1280,960));temp.replace(target)
    preview=DEST/'preview_12s.mp4'
    if force or not completed(preview,17*FPS,(1280,960)) or target.stat().st_mtime>preview.stat().st_mtime:
        prepend_warning(target,preview,(1280,960),12,audio_source=SOURCE,audio_start=45,body_start=50)
    for i,(_,name,_,_,_) in enumerate(ITEMS):
        poster=DEST/(Path(name).stem+'.jpg')
        run([FFMPEG,'-hide_banner','-loglevel','error','-y','-ss',str(51+(5 if i<3 else 0)),
             '-i',str(DEST/name),'-frames:v','1','-q:v','2',str(poster)])
    run([FFMPEG,'-hide_banner','-loglevel','error','-y','-ss','56','-i',str(target),
         '-frames:v','1','-q:v','2',str(DEST/'comparison.jpg')])

def gallery():
    DEST.mkdir(exist_ok=True);cards=[]
    for i,(_,name,title,_,detail) in enumerate(ITEMS):
        poster=Path(name).stem+'.jpg';notice='含5秒静态光敏性癫痫警告片头。' if i<3 else ''
        cards.append(f'<section><h2>{title}</h2><video controls playsinline preload="metadata" poster="{poster}" src="{name}"></video><p>{detail}{notice}</p><a href="{name}" download>下载完整视频</a></section>')
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Bad Apple · 四种计算图形</title><style>body{margin:0;padding:32px;background:#080d17;color:#e9f1f7;font:16px/1.75 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1280px;margin:auto}h1{font-size:32px;font-weight:500;margin:0}h2{font-size:22px;font-weight:500;margin:30px 0 14px}p{color:#aabecf}a{color:#73d8e9}video{display:block;width:100%;background:#060b14}section{min-width:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:32px}footer{margin-top:48px;color:#8da4b8;font-size:14px}nav{margin:16px 0 22px}nav a{margin-right:20px}@media(max-width:800px){body{padding:18px}.grid{grid-template-columns:1fr}h1{font-size:26px}}</style><main><h1>Bad Apple · 四种计算图形</h1><p>四部完整实验视频 / 原曲同步 / 960×720 / 30fps。A、B、C片头含5秒静态光敏性癫痫警告。</p><nav><a href="00_four_way_comparison.mp4" download>下载四画面对比版</a><a href="validation.json">查看输出校验</a><a href="project.json">算法与复现信息</a></nav><p>以下对比版也包含5秒警告；左上A、右上B、左下C、右下D。</p><video controls playsinline preload="metadata" poster="comparison.jpg" src="00_four_way_comparison.mp4"></video><div class="grid">'''+''.join(cards)+'''</div><footer>原作动画：あにら（Anira）。音乐：Bad Apple!! feat.nomico / Alstroemeria Records。<br>以上为算法可视化实验，不构成全网首创声明。<br>素材来源：<a href="https://github.com/NPCat/bad-apple-bot">NPCat/bad-apple-bot</a>。源码与说明：<a href="https://github.com/CS-LX/bad-apple-graphics-lab">GitHub</a>。观看时播放一个视频会暂停其他视频。</footer></main><script>document.querySelectorAll('video').forEach(v=>v.addEventListener('play',()=>{document.querySelectorAll('video').forEach(o=>{if(o!==v)o.pause();});}));</script></html>'''
    (DEST/'index.html').write_text(html,encoding='utf8')
    data={'source':'https://github.com/NPCat/bad-apple-bot','source_video_frames':SOURCE_FRAMES,
          'source_video_duration_seconds':SOURCE_FRAMES/FPS,'warning_seconds':WARNING_SECONDS,
          'warning_applies_to':['A','B','C','comparison','preview'],
          'warning_reference':'https://www.epilepsy.com/what-is-epilepsy/seizure-triggers/photosensitivity',
          'audio':'A/B/C and comparison: source delayed by 5 seconds and encoded once to AAC 192k. D: original AAC copied.',
          'algorithms':[{'video':name,'title':title,'description':detail} for _,name,title,_,detail in ITEMS],
          'reproduce_all':'python scripts/render_all.py','dependencies':'requirements.txt; FFmpeg and ffprobe on PATH, or FFMPEG_BIN/FFPROBE_BIN.',
          'source_code':'https://github.com/CS-LX/bad-apple-graphics-lab',
          'novelty':'No claim of worldwide priority; these are specific algorithm visualization experiments.'}
    (DEST/'project.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gallery-only',action='store_true');p.add_argument('--mux-only',action='store_true')
    p.add_argument('--force',action='store_true');p.add_argument('--only',nargs='+',choices=list('ABCD'))
    a=p.parse_args()
    if not a.gallery_only:
        print(json.dumps(mux(a.only,a.force),indent=2),flush=True)
        if not a.mux_only:comparison(a.force)
    gallery();print('DELIVERABLES: '+str(DEST),flush=True)
