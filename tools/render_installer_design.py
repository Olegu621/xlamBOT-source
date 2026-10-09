from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math

out = Path(__file__).resolve().parents[1] / 'installer/design'
out.mkdir(parents=True, exist_ok=True)
w, h = 656, 1256
im = Image.new('RGB', (w,h))
pixels = im.load()
for y in range(h):
    for x in range(w):
        glow = math.exp(-(((x-350)/330)**2 + ((y-565)/395)**2))
        pixels[x,y] = (int(17+25*glow), int(19+11*glow), int(30+52*glow))
d = ImageDraw.Draw(im)
def font(size, bold=False):
    return ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',size)
for y in range(48,h,56):
    for x in range(48,w,56): d.ellipse((x,y,x+2,y+2),fill=(50,44,74))
d.text((64,91),'xlamBOT',font=font(68,True),fill='#f5f3ff')
d.rounded_rectangle((64,196,350,238),radius=21,fill='#302647',outline='#554272',width=2)
d.text((86,201),'WINDOWS EDITION',font=font(22,True),fill='#c6b1ef')
cx,cy=328,608
for r in (248,215,181):
    d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(70+(248-r)//3,48,111),width=2)
d.arc((cx-248,cy-248,cx+248,cy+248),230,286,fill='#ac7df8',width=5)
d.arc((cx-215,cy-215,cx+215,cy+215),20,65,fill='#8a65d8',width=4)
for angle,r in [(249,248),(52,215),(141,181)]:
    x=cx+r*math.cos(math.radians(angle)); y=cy+r*math.sin(math.radians(angle))
    d.ellipse((x-7,y-7,x+7,y+7),fill='#c6a5ff')
d.rounded_rectangle((193,473,463,743),radius=78,fill='#241c39',outline='#68508e',width=3)
d.line((259,543,397,681),fill='#c1a2ff',width=38)
d.line((397,543,259,681),fill='#c1a2ff',width=38)
d.line((268,544,387,663),fill='#f2eaff',width=8)
d.text((64,1021),'READY TO PLAY.',font=font(38,True),fill='#f4efff')
d.text((64,1083),'We handle the rest.',font=font(27),fill='#aaa0bc')
d.line((64,1156,592,1156),fill='#3b314d',width=2)
d.text((64,1180),'01 / SETUP',font=font(22,True),fill='#9984b4')
im.save(out/'rail-en.bmp',optimize=True)
# Compact mark used on progress pages.
mark=Image.new('RGBA',(112,112),(0,0,0,0)); md=ImageDraw.Draw(mark)
md.rounded_rectangle((4,4,108,108),radius=29,fill='#2c2242',outline='#7959a8',width=2)
md.line((32,32,80,80),fill='#c1a2ff',width=14)
md.line((80,32,32,80),fill='#c1a2ff',width=14)
mark.save(out/'mark.png',optimize=True)
print('Created installer graphics')
