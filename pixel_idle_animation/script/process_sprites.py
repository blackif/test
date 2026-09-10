from __future__ import annotations

import math
import shutil
import sys
import zipfile
from collections import Counter, deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
OLD_DIR = ROOT / "old"

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
GRID = 4
CANVAS_SIZE = 1024
CELL_SIZE = 256
FRAME_COUNT = 16
GIF_DURATION_MS = 150  # 16 frames ~= 2.4 seconds

CHECKER_COLOR_DISTANCE = 28
CHECKER_MIN_LIGHTNESS = 150
CHECKER_MIN_BORDER_RATIO = 0.20
CHECKER_SAMPLE_STEP = 4


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def is_light_neutral(rgb: tuple[int, int, int]) -> bool:
    return min(rgb) >= CHECKER_MIN_LIGHTNESS and max(rgb) - min(rgb) <= 25


def detect_checker_colors(image: Image.Image) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """Detect two common light neutral colors on the image border."""
    rgb = image.convert("RGB")
    width, height = rgb.size
    band = max(4, min(width, height) // 32)
    samples: list[tuple[int, int, int]] = []

    for y in range(0, min(height, band), CHECKER_SAMPLE_STEP):
        for x in range(0, width, CHECKER_SAMPLE_STEP):
            samples.append(rgb.getpixel((x, y)))
            samples.append(rgb.getpixel((x, height - 1 - y)))
    for x in range(0, min(width, band), CHECKER_SAMPLE_STEP):
        for y in range(0, height, CHECKER_SAMPLE_STEP):
            samples.append(rgb.getpixel((x, y)))
            samples.append(rgb.getpixel((width - 1 - x, y)))

    neutral = [c for c in samples if is_light_neutral(c)]
    if not neutral:
        return None

    counts = Counter(neutral)
    candidates = [color for color, _ in counts.most_common(20)]
    if len(candidates) < 2:
        return None

    first = candidates[0]
    if counts[first] / len(samples) < CHECKER_MIN_BORDER_RATIO:
        return None

    second = next(
        (candidate for candidate in candidates[1:] if color_distance(first, candidate) >= 20),
        None,
    )
    if second is None or counts[second] / len(samples) < CHECKER_MIN_BORDER_RATIO:
        return None

    distance = color_distance(first, second)
    if not 20 <= distance <= 180:
        return None

    return first, second


def remove_checkerboard_background(image: Image.Image) -> Image.Image:
    """Remove a border-connected light checkerboard and make it transparent."""
    image = image.convert("RGBA")
    checker = detect_checker_colors(image)
    if checker is None:
        return image

    color_a, color_b = checker
    width, height = image.size
    pixels = image.load()

    def is_candidate(x: int, y: int) -> bool:
        r, g, b, a = pixels[x, y]
        if a == 0:
            return True
        rgb = (r, g, b)
        return (
            color_distance(rgb, color_a) <= CHECKER_COLOR_DISTANCE
            or color_distance(rgb, color_b) <= CHECKER_COLOR_DISTANCE
        )

    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def add(x: int, y: int) -> None:
        index = y * width + x
        if not visited[index] and is_candidate(x, y):
            visited[index] = 1
            queue.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)

    while queue:
        x, y = queue.popleft()
        pixels[x, y] = (0, 0, 0, 0)
        if x > 0:
            add(x - 1, y)
        if x + 1 < width:
            add(x + 1, y)
        if y > 0:
            add(x, y - 1)
        if y + 1 < height:
            add(x, y + 1)

    removed = sum(visited)
    if removed < width * height * 0.05:
        return image.copy()

    print(
        f"Detected checkerboard background: {color_a} / {color_b}; "
        f"removed {removed:,} connected pixels."
    )
    return image


def prepare_sheet(image: Image.Image) -> Image.Image:
    """Return a 1024x1024 RGBA sprite sheet."""
    image = image.convert("RGBA")
    if image.size != (CANVAS_SIZE, CANVAS_SIZE):
        if image.width != image.height:
            raise ValueError(f"sprite sheet must be square, got {image.size}")
        image = image.resize((CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.NEAREST)
    return remove_checkerboard_background(image)


def extract_frames(sheet: Image.Image, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []
    for index in range(FRAME_COUNT):
        row, col = divmod(index, GRID)
        box = (col * CELL_SIZE, row * CELL_SIZE, (col + 1) * CELL_SIZE, (row + 1) * CELL_SIZE)
        frame = sheet.crop(box)
        path = output_dir / f"frame_{index + 1:02d}.png"
        frame.save(path, "PNG")
        frame_paths.append(path)
    return frame_paths


def make_gif(frame_paths: list[Path], gif_path: Path) -> None:
    """Create a looping GIF with a real transparent palette entry."""
    prepared: list[Image.Image] = []
    for path in frame_paths:
        rgba = Image.open(path).convert("RGBA")
        alpha = rgba.getchannel("A")
        rgba.putalpha(alpha.point(lambda a: 255 if a >= 128 else 0))
        prepared.append(rgba)

    paletted: list[Image.Image] = []
    transparent_rgb = (255, 0, 255)

    for rgba in prepared:
        rgb = Image.new("RGB", rgba.size, transparent_rgb)
        rgb.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
        p = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
        transparent_index = p.getpixel((0, 0))
        if transparent_index != 0:
            palette = p.getpalette()
            a = transparent_index * 3
            palette[a:a + 3], palette[0:3] = palette[0:3], palette[a:a + 3]
            p.putpalette(palette)
            pixels = p.load()
            for y in range(p.height):
                for x in range(p.width):
                    if pixels[x, y] == transparent_index:
                        pixels[x, y] = 0
                    elif pixels[x, y] == 0:
                        pixels[x, y] = transparent_index
        p.info["transparency"] = 0
        paletted.append(p)

    paletted[0].save(
        gif_path,
        save_all=True,
        append_images=paletted[1:],
        duration=GIF_DURATION_MS,
        loop=0,
        disposal=2,
        transparency=0,
    )


def make_zip(frame_paths: list[Path], zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in frame_paths:
            zf.write(path, arcname=path.name)


def process_image(input_path: Path) -> None:
    print(f"Processing: {input_path.name}")
    with Image.open(input_path) as image:
        sheet = prepare_sheet(image)
        work_dir = OUTPUT_DIR / input_path.stem
        frames_dir = work_dir / "frames"
        work_dir.mkdir(parents=True, exist_ok=True)
        frame_paths = extract_frames(sheet, frames_dir)
        make_gif(frame_paths, work_dir / f"{input_path.stem}.gif")
        make_zip(frame_paths, work_dir / f"{input_path.stem}_frames.zip")

    destination = OLD_DIR / input_path.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    shutil.move(str(input_path), str(destination))
    print(f"Moved to old: {destination}")


def main() -> int:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OLD_DIR.mkdir(parents=True, exist_ok=True)
    images = sorted(p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)
    if not images:
        print("No image files found in input/. Nothing to process.")
        return 0

    failed = 0
    for image_path in images:
        try:
            process_image(image_path)
        except Exception as exc:
            failed += 1
            print(f"ERROR: {image_path.name}: {exc}", file=sys.stderr)

    if failed:
        print(f"Finished with {failed} failed file(s).", file=sys.stderr)
        return 1
    print(f"Successfully processed {len(images)} image(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
