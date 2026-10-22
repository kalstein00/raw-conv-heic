"""Inspect embedded ARW previews to select representative scenes (no RAW conversion)."""
import argparse
import io
from pathlib import Path
from PIL import Image, ImageDraw, TiffImagePlugin

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('samples', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
files = sorted(args.samples.glob('*.ARW'))
if not files:
    raise ValueError('No ARW files')
sheet = Image.new('RGB', (1200, 240 * ((len(files) + 4) // 5)), '#222222')
draw = ImageDraw.Draw(sheet)
for index, path in enumerate(files):
    with path.open('rb') as stream:
        header = stream.read(8)
        if header[:4] != b'II*\x00':
            raise ValueError('Unsupported ARW TIFF header')
        stream.seek(int.from_bytes(header[4:8], 'little'))
        tags = TiffImagePlugin.ImageFileDirectory_v2(header)
        tags.load(stream)
        stream.seek(tags[513])
        preview = Image.open(io.BytesIO(stream.read(tags[514]))).convert('RGB')
        orientation = tags.get(274, 1)
        rotations = {1: None, 3: Image.Transpose.ROTATE_180, 6: Image.Transpose.ROTATE_270, 8: Image.Transpose.ROTATE_90}
        if orientation not in rotations:
            raise ValueError('Unsupported preview orientation')
        if rotations[orientation] is not None:
            preview = preview.transpose(rotations[orientation])
        preview.thumbnail((230, 210))
        x, y = index % 5 * 240, index // 5 * 240
        sheet.paste(preview, (x + (240 - preview.width) // 2, y))
        draw.text((x + 5, y + 215), path.stem, fill='white')
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open('xb') as stream:
    sheet.save(stream, format='JPEG', quality=90)
