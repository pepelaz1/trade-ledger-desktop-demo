"""Render local Windows font samples for visual comparison."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONTS = [
    ('Bahnschrift', 'bahnschrift.ttf'),
    ('Calibri', 'calibri.ttf'),
    ('Candara', 'Candara.ttf'),
    ('Arial', 'arial.ttf'),
    ('Corbel', 'corbel.ttf'),
    ('Cambria', 'cambria.ttc'),
    ('Tahoma', 'tahoma.ttf'),
    ('Trebuchet MS', 'trebuc.ttf'),
    ('Verdana', 'verdana.ttf'),
    ('Georgia', 'georgia.ttf'),
]
DIR = Path(r'C:\Windows\Fonts')
OUT = Path(__file__).resolve().parents[1] / 'screenshots' / 'font-options.png'
OUT.parent.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (1480, 1440), '#F1F5FA')
draw = ImageDraw.Draw(image)
regular = ImageFont.truetype(DIR / 'arial.ttf', 24)
heading = ImageFont.truetype(DIR / 'arialbd.ttf', 37)
small = ImageFont.truetype(DIR / 'arial.ttf', 19)
draw.text((42, 30), '10 вариантов шрифта', font=heading, fill='#142435')
draw.text((44, 82), 'Одинаковый текст и размер. Выбрать шрифт можно в верхней части приложения.',
          font=regular, fill='#526A7D')
for index, (name, filename) in enumerate(FONTS, 1):
    top = 130 + (index - 1) * 128
    draw.rounded_rectangle((38, top, 1442, top + 116), radius=18,
                           fill='white', outline='#D7E0EA', width=2)
    draw.rounded_rectangle((57, top + 24, 109, top + 74), radius=12, fill='#E2EFFF')
    number = str(index)
    bounds = draw.textbbox((0, 0), number, font=regular)
    draw.text((83 - (bounds[2]-bounds[0])/2, top+34), number, font=regular, fill='#1769A8')
    draw.text((128, top + 19), name, font=regular, fill='#526A7D')
    face = ImageFont.truetype(DIR / filename, 33)
    face_small = ImageFont.truetype(DIR / filename, 22)
    draw.text((440, top + 13), 'Журнал сделок · 2 400 000 ₽', font=face, fill='#142435')
    draw.text((442, top + 66), 'Прибыль +$1,248.56   ·   24 ноября 2026',
              font=face_small, fill='#306785')
image.save(OUT)
print(OUT)
