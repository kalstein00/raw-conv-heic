"""Inventory TIFF tags without decoding ARW pixels or opening HIF content."""
import argparse
import json
from pathlib import Path
from PIL import TiffImagePlugin

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory', type=Path)
parser.add_argument('report', type=Path)
args = parser.parse_args()
files = list(args.directory.iterdir())
raws = sorted(p for p in files if p.suffix.upper() == '.ARW')
hifs = {p.stem.casefold(): p.name for p in files if p.suffix.upper() == '.HIF'}
records = []
for path in raws:
    with path.open('rb') as stream:
        header = stream.read(8)
        if header[:4] != b'II*\x00':
            raise ValueError('Inventory supports little-endian TIFF ARW only')
        stream.seek(int.from_bytes(header[4:8], 'little'))
        top = TiffImagePlugin.ImageFileDirectory_v2(header)
        top.load(stream)
        subimages = []
        for offset in top.get(330, ()):
            stream.seek(offset)
            sub = TiffImagePlugin.ImageFileDirectory_v2(header)
            sub.load(stream)
            subimages.append({name: sub.get(tag) for name, tag in
                              [('width', 256), ('height', 257), ('bits_per_sample', 258),
                               ('compression_code', 259), ('crop_origin', 50719), ('crop_size', 50720)]})
        records.append({'name': path.name, 'hif': hifs.get(path.stem.casefold()),
                        'model': top.get(272), 'orientation': top.get(274), 'raw_ifds': subimages,
                        'compression_mode': 'unconfirmed; numeric TIFF code is not a mode identification'})
report = {'arw_count': len(raws), 'hif_count': len(hifs),
          'unmatched_arw': [r['name'] for r in records if r['hif'] is None],
          'unmatched_hif': sorted(name for stem, name in hifs.items() if stem not in {p.stem.casefold() for p in raws}),
          'records': records}
args.report.parent.mkdir(parents=True, exist_ok=True)
with args.report.open('x', encoding='utf-8') as stream:
    json.dump(report, stream, indent=2)
print(json.dumps({k: v for k, v in report.items() if k != 'records'}, indent=2))
