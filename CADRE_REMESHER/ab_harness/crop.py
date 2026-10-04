"""crop.py <render prefix> <out.png> <n slots> <x0 x1 y0 y1 as fractions of one slot> : cut the same window out of every slot of the first view and put them side by side"""
import sys, json
from PIL import Image
prefix, out, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
x0, x1, y0, y1 = [float(v) for v in sys.argv[4:8]]
view = int(sys.argv[8]) if len(sys.argv) > 8 else 0
info = json.load(open(prefix + '_info.json'))
im = Image.open(list(info['views'].values())[view]['path']).convert('RGB')
w, h = im.size; sw = w / n
tiles = [im.crop((int(k * sw + x0 * sw), int(y0 * h), int(k * sw + x1 * sw), int(y1 * h))) for k in range(n)]
sheet = Image.new('RGB', (sum(t.width for t in tiles) + 10 * (n - 1), tiles[0].height), 'white')
x = 0
for t in tiles:
    sheet.paste(t, (x, 0)); x += t.width + 10
sheet.save(out); print(out, sheet.size)
