"""Static warning cards; no flashing, countdown animation, or audio."""
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont
from video_common import ROOT

WARNING_SECONDS = 5

def warning_card(size=(960, 720)):
    candidates = [os.environ.get('FONT_FILE', ''),
                  'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  '/System/Library/Fonts/PingFang.ttc']
    font_path = next((p for p in candidates if p and Path(p).is_file()), None)
    chinese = font_path is not None
    if not font_path:
        from video_common import find_font
        font_path = find_font()
    scale = size[0] / 960
    def font(px):
        return (ImageFont.truetype(str(font_path), round(px * scale)) if font_path
                else ImageFont.load_default(size=round(px * scale)))
    im = Image.new('RGB', size, (9, 14, 22)); d = ImageDraw.Draw(im)
    cx, cy = size[0] / 2, size[1] / 2
    def line(text, y, px, color):
        d.text((cx, cy + y * scale), text, anchor='mm', font=font(px), fill=color)
    d.rounded_rectangle((48*scale, cy-225*scale, size[0]-48*scale, cy+225*scale),
                        radius=12*scale, outline=(50, 61, 75), width=max(1, round(scale)))
    line('光敏性癫痫警告' if chinese else 'PHOTOSENSITIVITY WARNING',
         -143, 37 if chinese else 31, (230, 192, 115))
    if chinese:
        lines = ['本视频含快速闪烁、强烈明暗变化与高对比图案。',
                 '这些画面可能诱发光敏性癫痫发作或其他不适。',
                 '对闪光敏感或有相关病史的观众，请勿继续观看。',
                 '如感到不适，请立即停止观看。']
    else:
        lines = ['Contains flashing lights and high-contrast patterns.',
                 'These may trigger photosensitive seizures or discomfort.',
                 'Do not continue if you are sensitive to flashing images.',
                 'Stop watching immediately if you feel unwell.']
    for i, text in enumerate(lines):
        line(text, -52+i*42, 25 if chinese else 24, (196, 205, 215))
    line('5 秒后进入正片' if chinese else 'Video begins after this 5-second notice',
         167, 20, (124, 142, 162))
    return im

def save_warning(size=(960, 720)):
    path = ROOT/'output'/f'warning_{size[0]}x{size[1]}.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    warning_card(size).save(path)
    return path
