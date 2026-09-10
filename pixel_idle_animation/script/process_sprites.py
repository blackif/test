from __future__ import annotations

import shutil
import sys
import zipfile
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


def prepare_sheet(image: Image.Image) -> Image.Image:
    """Return a 1024x1024 RGBA sprite sheet."""
    image = image.convert("RGBA")
    if image.size != (CANVAS_SIZE, CANVAS_SIZE):
        if image.width != image.height:
            raise ValueError(f"sprite sheet must be square, got {image.size}")
        image = image.resize((CANVAS_SIZE, CANVAS_SIZE), Image.Resampling.NEAREST)
    return image


def extract_frames(sheet: Image.Image, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_paths: list[Path] = []

    for index in range(FRAME_COUNT):
        row, col = divmod(index, GRID)
        box = (
            col * CELL_SIZE,
            row * CELL_SIZE,
            (col + 1) * CELL_SIZE,
            (row + 1) * CELL_SIZE,
        )
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
        # GIF supports binary transparency, so alpha below 128 becomes transparent.
        rgba.putalpha(alpha.point(lambda a: 255 if a >= 128 else 0))
        prepared.append(rgba)

    paletted: list[Image.Image] = []
    transparent_rgb = (255, 0, 255)

    for rgba in prepared:
        rgb = Image.new("RGB", rgba.size, transparent_rgb)
        rgb.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
        p = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)

        # The top-left pixel is inside the required transparent padding, so its
        # palette index identifies the transparent color. Swap it to index 0.
        transparent_index = p.getpixel((0, 0))
        if transparent_index != 0:
            palette = p.getpalette()
            a = transparent_index * 3
            b = 0
            palette[a:a + 3], palette[b:b + 3] = palette[b:b + 3], palette[a:a + 3]
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

        # Keep each input's results isolated so multiple inputs do not overwrite.
        work_dir = OUTPUT_DIR / input_path.stem
        frames_dir = work_dir / "frames"
        work_dir.mkdir(parents=True, exist_ok=True)

        frame_paths = extract_frames(sheet, frames_dir)
        gif_path = work_dir / f"{input_path.stem}.gif"
        zip_path = work_dir / f"{input_path.stem}_frames.zip"
        make_gif(frame_paths, gif_path)
        make_zip(frame_paths, zip_path)

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

    images = sorted(
        p for p in INPUT_DIR.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED
    )

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
