"""Stack the per-view renders into one labelled sheet (system python3 + PIL).

python3 montage.py <prefix> <out.png> <title> [caption per label, '|' separated lines] ...
"""
import sys, json
from PIL import Image, ImageDraw, ImageFont

prefix, out, title = sys.argv[1], sys.argv[2], sys.argv[3]
caps = sys.argv[4:]
info = json.load(open(prefix + '_info.json'))
labels = info['labels']
n = len(labels)

def font(sz):
    for p in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()

imgs = [Image.open(v['path']).convert('RGB') for v in info['views'].values()]
W = max(i.width for i in imgs)
head = 150 + 26 * max((c.count('|') + 1 for c in caps), default=0)
H = head + sum(i.height for i in imgs)
sheet = Image.new('RGB', (W, H), 'white')
d = ImageDraw.Draw(sheet)
d.text((20, 12), title, fill='black', font=font(40))
d.text((20, 62), "dots = poles:  red = 3 edges meet,  blue = 5 edges meet,  magenta = 6+", fill=(90, 90, 90), font=font(22))
slot = W / n
for i, lab in enumerate(labels):
    x = int(i * slot + 20)
    d.text((x, 100), lab, fill='black', font=font(34))
    if i < len(caps):
        for k, line in enumerate(caps[i].split('|')):
            d.text((x, 146 + 26 * k), line, fill=(40, 40, 40), font=font(21))
y = head
for im in imgs:
    sheet.paste(im, ((W - im.width) // 2, y))
    y += im.height
sheet.save(out)
print("wrote", out, sheet.size)
