from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

import numpy as np
import rawpy

from ._verify import verify_heic


@dataclass(frozen=True)
class ConversionResult:
    status: str
    output: Path
    verification: dict[str, Any] | None = None


def _fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'sha256': digest, 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def convert_raw(source: Path, output: Path) -> ConversionResult:
    """Single-input proof seam. Failures raise; only verified files are published."""
    source, output = source.resolve(), output.absolute()
    if output.exists():
        return ConversionResult('skipped_existing', output)
    before = _fingerprint(source)
    started = time.monotonic()
    root = Path(__file__).resolve().parents[2]
    encoder = root / '.tools/build-uhdr/Release/ultrahdr_app.exe'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.rawhdr-', dir=output.parent) as directory:
        scratch = Path(directory)
        with rawpy.imread(str(source)) as raw:
            sizes = raw.sizes
            pixels = raw.postprocess(output_bps=16, gamma=(1, 1), no_auto_bright=True,
                                     use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB,  # type: ignore[attr-defined]
                                     bright=0.25, user_flip=0)
            x, y = sizes.crop_left_margin, sizes.crop_top_margin
            width, height = sizes.crop_width, sizes.crop_height
            if width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > pixels.shape[1] or y + height > pixels.shape[0]:
                raise ValueError('Unsupported or invalid visible RAW crop')
            pixels = pixels[y:y + height, x:x + width]
            rotations = {0: 0, 3: 2, 5: 1, 6: -1}
            if sizes.flip not in rotations:
                raise ValueError('Unsupported RAW orientation')
            pixels = np.rot90(pixels, rotations[sizes.flip])
            raw_info = {'raw_width': sizes.raw_width, 'raw_height': sizes.raw_height,
                        'crop': [x, y, width, height], 'libraw_flip': sizes.flip,
                        'linear_intermediate_bits': 16, 'bright': 0.25,
                        'linear_scale': 16.0, 'intermediate_clipped_channels': int(np.count_nonzero(pixels == 65535))}
        height, width = pixels.shape[:2]
        # High precision linear RGB produces BOTH intents. No clipped SDR is
        # expanded to invent the HDR intent. Exposure/tone policy is PoC-only.
        with (scratch / 'hdr.raw').open('wb') as hdr_file, (scratch / 'sdr.raw').open('wb') as sdr_file:
            for row in range(0, height, 128):
                hdr = pixels[row:row + 128].astype(np.float32) * (16.0 / 65535.0)
                luminance = hdr @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
                sdr_linear = np.clip(hdr / (1.0 + luminance[..., None]), 0, 1)
                sdr = np.where(sdr_linear <= 0.0031308, sdr_linear * 12.92,
                               1.055 * np.power(sdr_linear, 1.0 / 2.4) - 0.055)
                rgba_hdr = np.ones((*hdr.shape[:2], 4), dtype=np.float16)
                rgba_hdr[..., :3] = hdr
                rgba_sdr = np.full((*hdr.shape[:2], 4), 255, dtype=np.uint8)
                rgba_sdr[..., :3] = np.rint(sdr * 255).astype(np.uint8)
                rgba_hdr.tofile(hdr_file)
                rgba_sdr.tofile(sdr_file)
        del pixels
        candidate = scratch / 'candidate.heic'
        env = dict(os.environ)
        env['PATH'] = str(root / '.tools/install/bin') + os.pathsep + env.get('PATH', '')
        command = [str(encoder), '-m', '0', '-p', str(scratch / 'hdr.raw'), '-y', str(scratch / 'sdr.raw'),
                   '-a', '4', '-b', '3', '-w', str(width), '-h', str(height), '-C', '0', '-c', '0',
                   '-t', '0', '-R', '1', '-q', '95', '-Q', '95', '-s', '1', '-M', '0', '-G', '1',
                   '-D', '0', '-z', str(candidate)]
        completed = subprocess.run(command, env=env, capture_output=True, timeout=600)
        if completed.returncode or not candidate.is_file():
            raise RuntimeError('HEIC encoder failed: ' + (completed.stdout + completed.stderr).decode('utf-8', errors='replace')[-4000:])
        verification = verify_heic(candidate)
        if (verification['width'], verification['height']) != (width, height):
            raise ValueError('Encoded dimensions differ from oriented RAW')
        if verification['hdr_max'] <= 1 or verification['changed_pixels'] == 0:
            raise ValueError('No independently reconstructed HDR signal')
        after = _fingerprint(source)
        if before != after:
            raise RuntimeError('Source changed during conversion')
        verification.update(source_before=before, source_after=after, raw=raw_info,
                            elapsed_seconds=time.monotonic() - started,
                            output_sha256=_fingerprint(candidate)['sha256'])
        # Same-volume hard link is atomic and fails if another writer wins.
        try:
            os.link(candidate, output)
        except FileExistsError:
            return ConversionResult('skipped_existing', output)
        return ConversionResult('success', output, verification)
