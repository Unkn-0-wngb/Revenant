import io
import math
import os
import struct
import sys
import zipfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import paths

ROOT = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(ROOT, "art")
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"

CARBON = (24, 26, 29)
TEAL = (0, 196, 172)
INK = (12, 13, 14)
PAPER = (242, 242, 238)
GUNMETAL = (92, 104, 112)


def game_data():
    folder = paths.game_data()
    if not folder:
        raise FileNotFoundError("TrackMania Nations Forever was not found")
    return folder


def font(size, weight=700, width=75):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([weight, width])
    except OSError:
        pass
    return f


def shear(image, lean, centre_y):
    return image.transform(image.size, Image.AFFINE, (1, lean, -lean * centre_y, 0, 1, 0), resample=Image.BICUBIC)


def slanted_box(x, y, w, h, lean):
    return [(x + lean * h, y), (x + w + lean * h, y), (x + w, y + h), (x, y + h)]


def fit_text(text, max_w, max_h, weight=700, width=75):
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = int(max_h * 1.4)
    while size > 4:
        f = font(size, weight, width)
        box = probe.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_w and box[3] - box[1] <= max_h:
            return f, box
        size -= 2
    f = font(4, weight, width)
    return f, probe.textbbox((0, 0), text, font=f)


def logo(size=1024, box=TEAL, letter_colour=INK):
    big = size * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    lean = 0.2
    h = big * 0.74
    w = big * 0.74 - lean * h
    x = (big - w - lean * h) / 2
    y = (big - h) / 2
    draw.polygon(slanted_box(x, y, w, h, lean), fill=box + (255,))

    letter = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    f, box = fit_text("R", w * 0.86, h * 0.8)
    lx = x + lean * h / 2 + (w - (box[2] - box[0])) / 2 - box[0]
    ly = y + (h - (box[3] - box[1])) / 2 - box[1]
    ImageDraw.Draw(letter).text((lx, ly), "R", font=f, fill=letter_colour + (255,))
    image.alpha_composite(shear(letter, lean * 0.8, big / 2))
    return image.resize((size, size), Image.LANCZOS)


def wordmark(width, height, text="REVENANT", colour=None, wide=75):
    big = 4
    image = Image.new("RGBA", (width * big, height * big), (0, 0, 0, 0))
    f, box = fit_text(text, width * big * 0.9, height * big * 0.86, width=wide)
    x = (width * big - (box[2] - box[0])) / 2 - box[0]
    y = (height * big - (box[3] - box[1])) / 2 - box[1]
    ImageDraw.Draw(image).text((x, y), text, font=f, fill=(colour or PAPER) + (255,))
    image = shear(image, 0.16, height * big / 2)
    return image.resize((width, height), Image.LANCZOS)


def signature(cap, box=TEAL, letter_colour=INK, text_colour=PAPER, wide=75):
    text = wordmark(cap * 8, int(cap * 1.4), "EVENANT", text_colour, wide)
    text = text.crop(text.getbbox())
    text = text.resize((round(text.width * cap / text.height), cap), Image.LANCZOS)
    badge = logo(cap * 3, box, letter_colour)
    badge = badge.crop(badge.getbbox())
    badge = badge.resize((round(badge.width * cap / badge.height), cap), Image.LANCZOS)
    space = round(cap * 0.035)
    image = Image.new("RGBA", (badge.width + space + text.width, cap), (0, 0, 0, 0))
    image.alpha_composite(badge, (0, 0))
    image.alpha_composite(text, (badge.width + space, 0))
    return image


def lockup(height=200, tagline="SELF-TAUGHT TRACKMANIA AI"):
    title = signature(int(height * 0.62))
    tag = wordmark(int(height * 2.4), int(height * 0.14), tagline, (150, 158, 160))
    tag = tag.crop(tag.getbbox())
    bar_h = max(3, int(height * 0.05))
    bar_w = int(height * 0.26)
    bar_y = title.height + int(height * 0.16)
    image = Image.new("RGBA", (max(title.width, bar_w + int(height * 0.1) + tag.width) + int(height * 0.05), height), (0, 0, 0, 0))
    image.alpha_composite(title, (0, 0))
    ImageDraw.Draw(image).polygon(slanted_box(0, bar_y, bar_w, bar_h, 0.6), fill=TEAL + (255,))
    image.alpha_composite(tag, (bar_w + int(height * 0.1), bar_y + bar_h // 2 - tag.height // 2))
    return image


def header(height=96):
    return signature(height)


def social_banner(path, width=1280, height=640):
    image = Image.new("RGBA", (width, height), INK + (255,))
    draw = ImageDraw.Draw(image)
    lean = 0.9
    draw.polygon(slanted_box(width * 0.52, 0, width * 0.10, height, lean * 0.5), fill=TEAL + (255,))
    draw.polygon(slanted_box(width * 0.65, 0, width * 0.025, height, lean * 0.5), fill=TEAL + (255,))
    draw.polygon(slanted_box(width * 0.70, 0, width * 0.012, height, lean * 0.5), fill=PAPER + (255,))
    sign = lockup(int(height * 0.3))
    image.alpha_composite(sign, (int(width * 0.07), (height - sign.height) // 2))
    image.convert("RGB").save(path, quality=95)


def dds_bytes(image, mipmaps=False):
    levels = [image]
    if mipmaps:
        while levels[-1].size[0] > 1 and levels[-1].size[1] > 1:
            w, h = levels[-1].size
            levels.append(levels[-1].resize((max(1, w // 2), max(1, h // 2)), Image.LANCZOS))
    chunks = []
    header = None
    for level in levels:
        out = io.BytesIO()
        level.save(out, format="DDS", pixel_format="DXT5")
        data = out.getvalue()
        header = header or bytearray(data[:128])
        chunks.append(data[128:])
    if mipmaps:
        flags = struct.unpack_from("<I", header, 8)[0] | 0x20000
        struct.pack_into("<I", header, 8, flags)
        struct.pack_into("<I", header, 28, len(levels))
        caps = struct.unpack_from("<I", header, 108)[0] | 0x400008
        struct.pack_into("<I", header, 108, caps)
    return bytes(header) + b"".join(chunks)


def save_logo_files():
    os.makedirs(ART, exist_ok=True)
    big = logo(1024)
    lockup(200).save(os.path.join(ART, "revenant_lockup.png"))
    header().save(os.path.join(ART, "revenant_header.png"))
    social_banner(os.path.join(ART, "revenant_banner.png"))
    big.save(os.path.join(ART, "revenant_logo.png"))
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(ART, "revenant_logo_256.png"))
    flag = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    flag.alpha_composite(big.resize((128, 128), Image.LANCZOS))
    with open(os.path.join(ART, "Revenant.dds"), "wb") as f:
        f.write(dds_bytes(flag))
    return big


def component_masks(layer, boxes):
    from scipy import ndimage

    alpha = np.asarray(Image.open(layer).convert("RGBA"))[:, :, 3] > 128
    labels, _ = ndimage.label(alpha)
    masks = []
    for x0, y0, x1, y1 in boxes:
        ids = np.unique(labels[y0:y1, x0:x1])
        ids = ids[ids > 0]
        best = max(ids, key=lambda i: (labels[y0:y1, x0:x1] == i).sum())
        masks.append(((x0, y0, x1, y1), labels == best))
    return masks


def axis(mask):
    ys, xs = np.nonzero(mask)
    points = np.column_stack([xs, ys]).astype(np.float64)
    centre = points.mean(axis=0)
    values, vectors = np.linalg.eigh(np.cov((points - centre).T))
    long_axis = vectors[:, np.argmax(values)]
    short_axis = np.array([-long_axis[1], long_axis[0]])
    along = (points - centre) @ long_axis
    across = (points - centre) @ short_axis
    angle = math.degrees(math.atan2(-long_axis[1], long_axis[0]))
    return centre, angle, along.max() - along.min(), across.max() - across.min()


def facing(angle, hint):
    options = [angle, angle + 180, angle - 180]
    return min(options, key=lambda a: abs((a - hint + 180) % 360 - 180))


def rounded_mask(size, box, radius):
    image = Image.new("L", size, 0)
    ImageDraw.Draw(image).rounded_rectangle(box, radius=radius, fill=255)
    return np.asarray(image) > 128


def stock_maps():
    folder = os.path.join(game_data(), "Skins", "Vehicles", "StadiumCar")
    names = sorted(name for name in os.listdir(folder) if name.lower().endswith(".zip"))
    stack = np.zeros((len(names), 2048, 2048, 4), np.uint8)
    for i, name in enumerate(names):
        with zipfile.ZipFile(os.path.join(folder, name)) as z:
            image = Image.open(io.BytesIO(z.read("Diffuse.dds"))).convert("RGBA")
        stack[i] = np.asarray(image.resize((2048, 2048), Image.LANCZOS))
    shade = np.zeros((2048, 2048), np.float32)
    spread = np.zeros((2048, 2048), np.float32)
    gloss = np.zeros((2048, 2048), np.uint8)
    for y in range(0, 2048, 128):
        part = stack[:, y:y + 128]
        shade[y:y + 128] = np.percentile(part[..., :3].max(axis=3), 92, axis=0) / 255
        spread[y:y + 128] = part[..., :3].astype(np.float32).std(axis=0).mean(axis=2)
        gloss[y:y + 128] = np.median(part[..., 3], axis=0)
    return shade, spread, gloss


def stripes(size, paintable):
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for centre, vertical, reach in ((1440, False, 2048), (1540, True, 860)):
        for side in (-1, 1):
            for near, far, colour in ((14, 62, TEAL), (74, 82, PAPER)):
                a, b = sorted((centre + side * near, centre + side * far))
                draw.rectangle((a, 0, b, reach) if vertical else (0, a, reach, b), fill=colour + (255,))
    keep = Image.fromarray((paintable * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(1.5))
    layer.putalpha(ImageChops.multiply(layer.split()[3], keep))
    return layer


def plate(skin, mask, content, hint, fill=TEAL, mirror=False, pad=0.16):
    shape = Image.fromarray((mask * 255).astype(np.uint8), "L")
    inner = shape.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.1))
    panel(skin, mask, fill)

    centre, angle, length, width = axis(mask)
    if mirror:
        content = content.transpose(Image.FLIP_LEFT_RIGHT)
    room_w, room_h = length - pad * 2 * width, width * (1 - pad * 2)
    scale = min(room_w / content.width, room_h / content.height)
    content = content.resize((max(1, round(content.width * scale)), max(1, round(content.height * scale))), Image.LANCZOS)
    content = content.rotate(facing(angle, hint), resample=Image.BICUBIC, expand=True)
    layer = Image.new("RGBA", skin.size, (0, 0, 0, 0))
    layer.alpha_composite(content, (round(centre[0] - content.width / 2), round(centre[1] - content.height / 2)))
    layer.putalpha(ImageChops.multiply(layer.split()[3], inner))
    skin.alpha_composite(layer)


def panel(skin, mask, fill=TEAL):
    shape = Image.fromarray((mask * 255).astype(np.uint8), "L")
    layer = Image.new("RGBA", skin.size, fill + (0,))
    layer.putalpha(shape.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(0.8)))
    skin.alpha_composite(layer)


def make_skin(mark):
    shade, spread, gloss = stock_maps()
    paint = Image.new("RGBA", (2048, 2048), CARBON + (255,))
    paint.alpha_composite(stripes(paint.size, spread > 45))
    rgb = np.asarray(paint, np.float32)[..., :3] * np.clip(shade[..., None] * 1.06, 0, 1)
    skin = Image.fromarray(rgb.astype(np.uint8), "RGB").convert("RGBA")

    layers = os.path.join(game_data(), "Painter", "Layers", "StadiumCar")
    stickers = dict(
        zip(
            ("right side", "left side", "nose right", "nose left", "wing tip top", "wing tip bottom"),
            (mask for _, mask in component_masks(
                os.path.join(layers, "Nations Stickers", "Diffuse.tga"),
                [(761, 1854, 1209, 1950), (762, 947, 1209, 1043), (1332, 636, 1396, 762), (839, 636, 903, 761), (1798, 896, 1866, 978), (1746, 988, 1818, 1062)],
            )),
        )
    )
    side = signature(240, INK, TEAL, INK, wide=100)
    plate(skin, stickers["right side"], side, 0, pad=0.17)
    plate(skin, stickers["left side"], side, 180, pad=0.17)
    panel(skin, stickers["nose left"])
    panel(skin, stickers["nose right"])
    panel(skin, stickers["wing tip top"])
    panel(skin, stickers["wing tip bottom"])
    (_, rear), = component_masks(os.path.join(layers, "AirPlate", "Diffuse.tga"), [(1727, 414, 1826, 834)])
    plate(skin, rear, side, -90, pad=0.16)
    plate(skin, rounded_mask(skin.size, (1256, 1381, 1358, 1428), 6), wordmark(600, 120, colour=TEAL), 0, fill=CARBON, mirror=True, pad=0.14)
    plate(skin, rounded_mask(skin.size, (1256, 1440, 1330, 1493), 6), mark, 0, fill=CARBON, pad=0.08)

    finish = np.asarray(skin).copy()
    finish[..., 3] = gloss
    skin = Image.fromarray(finish, "RGBA")
    icon = Image.new("RGBA", (128, 128), CARBON + (255,))
    icon.alpha_composite(mark.resize((112, 112), Image.LANCZOS), (8, 8))
    target = os.path.join(ART, "Revenant.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Diffuse.dds", dds_bytes(skin, mipmaps=True))
        z.writestr("Icon.dds", dds_bytes(icon))
    preview = Image.new("RGB", skin.size, (0, 0, 0))
    preview.paste(skin.convert("RGB"))
    preview.resize((1024, 1024), Image.LANCZOS).save(os.path.join(ART, "revenant_skin_preview.png"))
    return target


if __name__ == "__main__":
    mark = save_logo_files()
    print("logo saved in", ART)
    if "--logo" not in sys.argv:
        print("skin saved as", make_skin(mark))
