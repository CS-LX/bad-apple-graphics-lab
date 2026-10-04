"""Bounded-memory FFmpeg I/O for the four computational Bad Apple videos."""
from pathlib import Path
import sys, subprocess, json, os, shutil
ROOT = Path(__file__).resolve().parents[1]
if (ROOT / '.preview-deps').is_dir():
    sys.path.insert(0, str(ROOT / '.preview-deps'))
import numpy as np

def find_tool(name, variable):
    """Use an explicit executable, then PATH, then the legacy Windows location.

    Leave a bare command name if no installation is found so that importing
    renderer modules and requesting --help never requires an FFmpeg install.
    A later subprocess call reports the missing executable when it is needed.
    """
    configured = os.environ.get(variable)
    if configured:
        return os.path.expandvars(os.path.expanduser(configured))
    found = shutil.which(name)
    if found:
        return found
    if os.name == 'nt':
        legacy = Path('C:/ffmpeg/bin') / (name + '.exe')
        if legacy.is_file():
            return str(legacy)
    return name

FFMPEG = find_tool('ffmpeg', 'FFMPEG_BIN')
FFPROBE = find_tool('ffprobe', 'FFPROBE_BIN')
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

def find_font():
    """Return a local font file, preferring FONT_FILE, without copying fonts."""
    configured = os.environ.get('FONT_FILE')
    if configured:
        font = Path(os.path.expandvars(configured)).expanduser()
        if not font.is_file():
            raise FileNotFoundError(f'FONT_FILE does not exist: {font}')
        return font
    candidates = [
        ROOT/'assets/label.ttf',
        Path('C:/Windows/Fonts/msyh.ttc'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        Path('/Library/Fonts/Arial.ttf'),
        Path('/System/Library/Fonts/Supplemental/Arial.ttf'),
        Path('C:/Windows/Fonts/segoeui.ttf'),
    ]
    return next((font for font in candidates if font.is_file()), None)

def probe(source):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-show_format','-of','json',str(source)],creationflags=CREATE_NO_WINDOW))

class VideoReader:
    def __init__(self,source,width,height,fps,start=0,duration=None):
        self.width,self.height=width,height
        cmd=[FFMPEG,'-hide_banner','-loglevel','error','-threads','2','-filter_threads','1']
        if start: cmd+=['-ss',str(start)]
        cmd+=['-i',str(source)]
        if duration is not None: cmd+=['-t',str(duration)]
        cmd+=['-an','-sn','-vf',f'fps={fps},scale={width}:{height}:flags=area','-pix_fmt','gray','-f','rawvideo','pipe:1']
        self.p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=width*height*3,creationflags=CREATE_NO_WINDOW)
    def __iter__(self): return self
    def __next__(self):
        need=self.width*self.height
        data=self.p.stdout.read(need)
        if not data:
            error=self.p.stderr.read().decode('utf8','replace')
            code=self.p.wait()
            if code: raise RuntimeError(f'FFmpeg decoder failed: {error}')
            raise StopIteration
        if len(data)!=need: raise RuntimeError(f'Partial video frame {len(data)}/{need}')
        return np.frombuffer(data,dtype=np.uint8).reshape(self.height,self.width)
    def close(self):
        if self.p.poll() is None: self.p.terminate()
        self.p.wait()

class VideoWriter:
    def __init__(self,path,width,height,fps,threads=2):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.path=path;self.width,self.height=width,height;self.count=0
        logpath=path.with_suffix('.ffmpeg.log')
        self.log=logpath.open('wb')
        cmd=[FFMPEG,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-threads',str(threads),'-pix_fmt','yuv420p','-movflags','+faststart',str(path)]
        self.p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.log,creationflags=CREATE_NO_WINDOW)
    def write(self,rgb):
        a=np.asarray(rgb,dtype=np.uint8)
        if a.shape!=(self.height,self.width,3): raise ValueError(f'Wrong frame shape: {a.shape}')
        self.p.stdin.write(np.ascontiguousarray(a).tobytes());self.count+=1
    def close(self):
        if self.p.stdin and not self.p.stdin.closed:self.p.stdin.close()
        code=self.p.wait();self.log.close()
        if code: raise RuntimeError(f'FFmpeg encoder failed ({code}); see {self.path.with_suffix(".ffmpeg.log")}')

def add_header(rgb,title,subtitle,counter=None):
    """Optional unobtrusive annotation; image algorithms need not use it."""
    from PIL import Image,ImageDraw,ImageFont
    im=Image.fromarray(rgb);d=ImageDraw.Draw(im)
    font=find_font()
    f=ImageFont.truetype(str(font),22) if font else ImageFont.load_default()
    small=ImageFont.truetype(str(font),15) if font else ImageFont.load_default()
    d.text((22,15),title,font=f,fill=(230,240,250),stroke_width=2,stroke_fill=(4,8,14))
    d.text((22,47),subtitle,font=small,fill=(154,177,196),stroke_width=1,stroke_fill=(4,8,14))
    if counter:d.text((22,im.height-28),str(counter),font=small,fill=(154,177,196))
    return np.asarray(im)
