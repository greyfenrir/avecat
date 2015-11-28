try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from PIL import Image, ImageFont, ImageDraw, ImageFilter
from openerp import tools
import base64

def get_grayscale(original):
    img = Image.open(StringIO.StringIO(original.decode('base64')))
    img = img.convert('LA')
    img = img.filter(ImageFilter.BLUR)

    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype('/usr/share/fonts/truetype/msttcorefonts/arial.ttf', 40)

    draw.text((12, 12), 'Preorder', font = font, fill = (208,208))
    draw.text((10, 10), 'Preorder', font = font, fill = (100,150))
    

    bs = StringIO.StringIO()
    img.save(bs, 'PNG')

    return base64.b64encode(bs.getvalue())
