import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image

from SessionActivity import ask


_LOGO_PATH = Path(__file__).resolve().parent.parent / "logo.png"
_SIXEL_WIDTH = 400
_SIXEL_COLORS = 16


def _encode_sixel_run(value, count):
    """Encode repeated Sixel pixels without needlessly enlarging the stream."""
    character = chr(63 + value)
    return f"!{count}{character}" if count >= 4 else character * count


@lru_cache(maxsize=1)
def _sixel_logo():
    """Turn the actual transparent PNG into a compact Sixel image."""
    with Image.open(_LOGO_PATH) as source:
        source = source.convert("RGBA")
        bounds = source.getbbox()
        if bounds is None:
            return ""
        source = source.crop(bounds)
        height = max(1, round(source.height * _SIXEL_WIDTH / source.width))
        image = source.resize((_SIXEL_WIDTH, height), Image.Resampling.LANCZOS)

    alpha = image.getchannel("A")

    rgb = image.convert("RGB").quantize(
        colors=_SIXEL_COLORS,
        method=Image.Quantize.FASTOCTREE,
    )
    palette = rgb.getpalette()
    indexes = list(rgb.getdata())
    opacity = list(alpha.getdata())
    used = sorted({index for index, value in zip(indexes, opacity) if value >= 16})


    sequence = [f"\x1bP0;1;0q\"1;1;{image.width};{image.height}"]
    for index in used:
        red, green, blue = palette[index * 3:index * 3 + 3]
        sequence.append(f"#{index};2;{red * 100 // 255};{green * 100 // 255};{blue * 100 // 255}")

    for top in range(0, image.height, 6):
        for index in used:
            values = []
            for x in range(image.width):
                bits = 0
                for offset in range(6):
                    y = top + offset
                    position = y * image.width + x
                    if y < image.height and opacity[position] >= 16 and indexes[position] == index:
                        bits |= 1 << offset
                values.append(bits)

            sequence.append(f"#{index}")
            run_value, run_count = values[0], 1
            for value in values[1:]:
                if value == run_value:
                    run_count += 1
                else:
                    sequence.append(_encode_sixel_run(run_value, run_count))
                    run_value, run_count = value, 1
            sequence.append(_encode_sixel_run(run_value, run_count))
            sequence.append("$")
        sequence.append("-")

    return "".join(sequence) + "\x1b\\"


def _show_logo():
    try:
        logo = _sixel_logo()
    except (OSError, ValueError):
        # make sure we dont crash if the logo cant be loaded or converted
        return False
    if not logo:
        return False

    sys.stdout.write(logo + "\n")
    sys.stdout.flush()
    return True


def ask_banner_menu(prompt):
    """Show only the real PNG logo directly above a Questionary menu."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        _show_logo()
    return ask(prompt)
