import io
import math
import os
import re
import struct
import sys
import zipfile

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import paths

ROOT = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(ROOT, "art")
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"

BLACK = (8, 10, 12)
CHARCOAL = (22, 26, 30)
TEAL = (25, 227, 200)
TEAL_DEEP = (8, 120, 112)
SILVER = (196, 204, 210)


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


def glow(layer, radius, strength=1.0):
    blurred = layer.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        alpha = blurred.split()[3].point(lambda a: min(255, int(a * strength)))
        blurred.putalpha(alpha)
    return blurred


def letter_r(size):
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    f = font(int(size * 0.78), 700, 75)
    box = draw.textbbox((0, 0), "R", font=f)
    x = (size - (box[2] - box[0])) // 2 - box[0] + int(size * 0.03)
    y = (size - (box[3] - box[1])) // 2 - box[1]
    draw.text((x, y), "R", font=f, fill=(255, 255, 255, 255))
    lean = 0.16
    return layer.transform(layer.size, Image.AFFINE, (1, lean, -lean * size / 2, 0, 1, 0), resample=Image.BICUBIC)


def logo(size=1024):
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    centre = size / 2
    radius = size * 0.46

    disc = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse((centre - radius, centre - radius, centre + radius, centre + radius), fill=BLACK + (255,))
    image.alpha_composite(disc)

    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    width = max(2, int(size * 0.022))
    ImageDraw.Draw(ring).ellipse((centre - radius, centre - radius, centre + radius, centre + radius), outline=TEAL + (255,), width=width)
    image.alpha_composite(glow(ring, size * 0.02, 1.4))
    image.alpha_composite(ring)

    r = letter_r(size)
    mask = r.split()[3]
    trail = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for i in range(1, 9):
        shifted = ImageChops.offset(mask, -int(size * 0.018 * i), 0).point(lambda a, i=i: int(a * (0.55 - i * 0.06)))
        ghost = Image.new("RGBA", (size, size), TEAL_DEEP + (0,))
        ghost.putalpha(shifted)
        trail.alpha_composite(ghost)
    clip = Image.new("L", (size, size), 0)
    ImageDraw.Draw(clip).ellipse((centre - radius + width, centre - radius + width, centre + radius - width, centre + radius - width), fill=255)
    trail.putalpha(ImageChops.multiply(trail.split()[3], clip))
    image.alpha_composite(trail)

    teal_r = Image.new("RGBA", (size, size), TEAL + (0,))
    teal_r.putalpha(mask)
    image.alpha_composite(glow(teal_r, size * 0.03, 1.6))
    white_r = Image.new("RGBA", (size, size), (240, 255, 252, 0))
    white_r.putalpha(mask)
    image.alpha_composite(white_r)
    return image


def wordmark(width, height, text="REVENANT"):
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    size = height
    while True:
        f = font(size, 700, 75)
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= width * 0.98 and box[3] - box[1] <= height * 0.9:
            break
        size -= 2
    x = (width - (box[2] - box[0])) // 2 - box[0]
    y = (height - (box[3] - box[1])) // 2 - box[1]
    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(text_layer).text((x, y), text, font=f, fill=TEAL + (255,))
    image.alpha_composite(glow(text_layer, max(1, height * 0.05), 1.3))
    ImageDraw.Draw(image).text((x, y), text, font=f, fill=(235, 252, 250, 255))
    return image


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
    big.save(os.path.join(ART, "revenant_logo.png"))
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(ART, "revenant_logo_256.png"))
    flag = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    flag.alpha_composite(big.resize((128, 128), Image.LANCZOS))
    with open(os.path.join(ART, "Revenant.dds"), "wb") as f:
        f.write(dds_bytes(flag))
    return big


def recolor(diffuse):
    rgba = np.asarray(diffuse.convert("RGBA")).astype(np.float32) / 255
    rgb, alpha = rgba[:, :, :3], rgba[:, :, 3:]
    high = rgb.max(axis=2, keepdims=True)
    low = rgb.min(axis=2, keepdims=True)
    sat = np.where(high > 0, (high - low) / np.maximum(high, 1e-6), 0)
    r, g, b = rgb[:, :, 0:1], rgb[:, :, 1:2], rgb[:, :, 2:3]
    redness = np.clip((r - np.maximum(g, b)) * 3, 0, 1)
    blueness = np.clip((b - np.maximum(r, g)) * 3, 0, 1)
    grey = np.asarray(SILVER, np.float32) / 255 * high * 0.92
    body = np.asarray(CHARCOAL, np.float32) / 255 * (0.6 + high * 1.4)
    accent = np.asarray(TEAL, np.float32) / 255 * np.clip(high * 1.15, 0, 1)
    coloured = (body * blueness + accent * redness) / np.maximum(blueness + redness, 1e-6)
    weight = np.clip(sat * 1.6, 0, 1) * np.clip(blueness + redness, 0, 1)
    out = grey * (1 - weight) + coloured * weight
    return Image.fromarray((np.concatenate([np.clip(out, 0, 1), alpha], axis=2) * 255).astype(np.uint8), "RGBA")


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


def plate(skin, mask, content, hint, mirror=False, pad=0.16):
    shape = Image.fromarray((mask * 255).astype(np.uint8), "L")
    outer = shape.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.1))
    inner = shape.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.1))
    for colour, alpha in ((TEAL, outer), (CHARCOAL, inner)):
        layer = Image.new("RGBA", skin.size, colour + (0,))
        layer.putalpha(alpha)
        skin.alpha_composite(layer)

    centre, angle, length, width = axis(mask)
    if mirror:
        content = content.transpose(Image.FLIP_LEFT_RIGHT)
    room_w, room_h = length * (1 - pad * 2 * width / length), width * (1 - pad * 2)
    scale = min(room_w / content.width, room_h / content.height)
    content = content.resize((max(1, round(content.width * scale)), max(1, round(content.height * scale))), Image.LANCZOS)
    content = content.rotate(facing(angle, hint), resample=Image.BICUBIC, expand=True)
    layer = Image.new("RGBA", skin.size, (0, 0, 0, 0))
    layer.alpha_composite(content, (round(centre[0] - content.width / 2), round(centre[1] - content.height / 2)))
    layer.putalpha(ImageChops.multiply(layer.split()[3], inner))
    skin.alpha_composite(layer)


def banner(width, height, mark):
    gap = height // 4
    small = mark.resize((height, height), Image.LANCZOS)
    words = wordmark(width - height - gap, int(height * 0.62))
    words = words.crop(words.getbbox())
    used = height + gap + words.width
    image = Image.new("RGBA", (used, height), (0, 0, 0, 0))
    image.alpha_composite(small, (0, 0))
    image.alpha_composite(words, (height + gap, (height - words.height) // 2))
    return image


def make_skin(mark):
    base = zipfile.ZipFile(os.path.join(game_data(), "Skins", "Vehicles", "StadiumCar", "GBR.zip"))
    skin = recolor(Image.open(io.BytesIO(base.read("Diffuse.dds"))))
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
    side = banner(1400, 220, mark)
    plate(skin, stickers["right side"], side, 0, pad=0.12)
    plate(skin, stickers["left side"], side, 180, pad=0.12)
    plate(skin, stickers["nose left"], mark, -90, pad=0.12)
    plate(skin, stickers["nose right"], mark, 90, pad=0.12)
    plate(skin, stickers["wing tip top"], mark, -90, pad=0.12)
    plate(skin, stickers["wing tip bottom"], mark, 0, pad=0.12)
    (_, rear), = component_masks(os.path.join(layers, "AirPlate", "Diffuse.tga"), [(1727, 414, 1826, 834)])
    plate(skin, rear, banner(1400, 220, mark), -90, pad=0.14)
    plate(skin, rounded_mask(skin.size, (1256, 1381, 1358, 1428), 8), wordmark(600, 120), 0, mirror=True, pad=0.14)
    plate(skin, rounded_mask(skin.size, (1256, 1440, 1330, 1493), 8), mark, 0, pad=0.08)

    icon = Image.new("RGBA", (128, 128), CHARCOAL + (255,))
    icon.alpha_composite(mark.resize((112, 112), Image.LANCZOS), (8, 8))
    target = os.path.join(ART, "Revenant.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Diffuse.dds", dds_bytes(skin, mipmaps=True))
        z.writestr("Icon.dds", dds_bytes(icon))
    skin.resize((1024, 1024), Image.LANCZOS).convert("RGB").save(os.path.join(ART, "revenant_skin_preview.png"))
    return target


if __name__ == "__main__":
    mark = save_logo_files()
    print("logo saved in", ART)
    if "--logo" not in sys.argv:
        print("skin saved as", make_skin(mark))
