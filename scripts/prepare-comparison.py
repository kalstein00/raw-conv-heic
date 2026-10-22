"""Private representative comparison bundle for issues #3/#4; not product UI."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import shutil

import pillow_heif
from PIL import Image

from rawhdr import convert_raw, verify_heic

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('samples', type=Path)
parser.add_argument('destination', type=Path)
parser.add_argument('stems', nargs='+')
args = parser.parse_args()
args.destination.mkdir(parents=True, exist_ok=False)
rows = []
for stem in args.stems:
    if Path(stem).name != stem or '/' in stem or '\\' in stem:
        raise ValueError('Expected sample stem, not a path')
    folder = args.destination / stem
    folder.mkdir()
    arw, hif = args.samples / (stem + '.ARW'), args.samples / (stem + '.HIF')
    hif_stat = hif.stat()
    with hif.open('rb') as stream:
        hif_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    output = folder / (stem + '.heic')
    result = convert_raw(arw, output, comparison_jpeg=folder / (stem + '.jpg'))
    if result.status != 'success':
        raise RuntimeError('Comparison requires newly generated, verified HEIC')
    independent = verify_heic(output, preview_path=folder / 'converted-sdr.png',
                              hdr_preview_path=folder / 'hdr-minus2ev.png', preview_max_size=8192)
    camera = pillow_heif.open_heif(hif, convert_hdr_to_8bit=True)
    profile = camera.info.get('nclx_profile', {})
    if (profile.get('color_primaries'), profile.get('transfer_characteristics')) != (1, 13):
        raise ValueError('Camera preview requires observed BT.709/sRGB HIF; do not guess HDR tone mapping')
    camera_image = camera.to_pillow()
    camera_image.load()
    camera_image.save(folder / 'camera-sdr.png', exif=b'', xmp=b'')
    exif = Image.Exif()
    exif.load(camera.info.get('exif', b''))
    exif_sub = exif.get_ifd(34665)
    fields = {'capture_time': 36867, 'iso': 34855, 'exposure': 33434,
              'aperture': 33437, 'lens': 42036, 'gps': 34853}
    original = {name: tag in exif or tag in exif_sub for name, tag in fields.items()}
    with hif.open('rb') as stream:
        after_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if hif_hash != after_hash or (hif_stat.st_size, hif_stat.st_mtime_ns) != (hif.stat().st_size, hif.stat().st_mtime_ns):
        raise RuntimeError('Camera HIF changed during comparison')
    shutil.copy2(hif, folder / (stem + '.HIF'))
    report = {'source_name': arw.name, 'status': result.status,
              'conversion': result.verification, 'independent': independent,
              'camera_hif': {'bytes': hif_stat.st_size, 'sha256': hif_hash, 'unchanged': True,
                             'width': camera.size[0], 'height': camera.size[1],
                             'bits': camera.info['bit_depth'], 'chroma': camera.info.get('chroma'),
                             'nclx': {k: profile[k] for k in ('color_primaries', 'transfer_characteristics', 'matrix_coefficients', 'full_range_flag')}},
              'heic_bytes': output.stat().st_size,
              'metadata': {'camera_presence': original, 'generated_capture_metadata_preserved': False,
                           'lost_fields': [name for name, present in original.items() if present],
                           'orientation': 'baked into pixels', 'color_management': 'explicit NCLX',
                           'warning': 'PoC HEIC/JPEG omit camera capture EXIF. Do not treat this as final metadata acceptance.'},
              'hdr_preview': 'SDR diagnostic: independent HDR reconstruction /4 (-2 EV), quarter resolution; not an HDR display proof'}
    (folder / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for preview_name in ('camera-sdr.png', 'converted-sdr.png', 'hdr-minus2ev.png'):
        with Image.open(folder / preview_name) as full_preview:
            full_preview.thumbnail((700, 700))
            full_preview.save(folder / (preview_name + '.preview.jpg'), quality=92)
    escaped = html.escape(stem)
    rows.append(f'<section><h2>{escaped}</h2><p><a href="{escaped}/{escaped}.HIF">Camera HIF</a> · <a href="{escaped}/{escaped}.heic">Gain Map HEIC</a> · <a href="{escaped}/{escaped}.jpg">Ultra HDR JPEG (comparison only)</a> · <a href="{escaped}/report.json">Report</a></p><div class="grid">' + ''.join(f'<figure><a href="{escaped}/{file}"><img src="{escaped}/{file}.preview.jpg"></a><figcaption>{label}</figcaption></figure>' for file,label in [('camera-sdr.png','Camera HIF → SDR preview'),('converted-sdr.png','Converted SDR base'),('hdr-minus2ev.png','Independent HDR /4: SDR diagnostic, NOT HDR display')]) + '</div></section>')
    print(json.dumps({'sample': stem, 'status': 'complete', 'hdr_max': independent['hdr_max'], 'shadow_delta': independent['shadow_mean_abs_change']}, ensure_ascii=False), flush=True)
page = '''<!doctype html><meta charset="utf-8"><title>Private RAW comparison</title><style>body{background:#252525;color:#eee;font:16px system-ui;margin:24px}a{color:#9bd1ff}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0}img{width:100%;height:520px;object-fit:contain;background:#181818}figcaption{padding:8px}section{margin:40px 0}p{line-height:1.6}</style><h1>Representative RAW comparison · #3 / #4</h1><p>Private local files. Click an image for full-size SDR inspection. The third column is an exposure-reduced SDR diagnostic, not actual HDR. Open the original HEIC/JPEG on Fold7 for the HDR acceptance check. Camera shooting EXIF is not preserved in generated files. No night sample is present.</p>'''
(args.destination / 'index.html').write_text(page + ''.join(rows), encoding='utf-8')
