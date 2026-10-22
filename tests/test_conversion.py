from pathlib import Path

import os
import pytest
import rawpy

from rawhdr import convert_raw


def test_existing_output_is_not_overwritten_or_claimed_as_verified(tmp_path: Path) -> None:
    source = tmp_path / "sample.ARW"
    source.write_bytes(b"input must not be decoded for a skipped output")
    output = tmp_path / "sample.heic"
    output.write_bytes(b"existing file, not a verified HDR image")
    before = output.stat()

    result = convert_raw(source, output)

    assert result.status == "skipped_existing"
    assert result.verification is None
    assert output.read_bytes() == b"existing file, not a verified HDR image"
    assert output.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.real_raw
@pytest.mark.skipif(not os.environ.get("RAWHDR_SAMPLE"), reason="private ARW not configured")
def test_real_arw_produces_independently_decoded_hdr_heic(tmp_path: Path) -> None:
    source = Path(os.environ["RAWHDR_SAMPLE"])
    before = source.stat()

    result = convert_raw(source, tmp_path / "result.heic")

    assert result.status == "success"
    assert result.verification is not None
    assert result.verification["decoder"] == "FFmpeg native HEVC + independent ISO reconstruction"
    assert (result.verification["width"], result.verification["height"]) == (4672, 7008)
    assert result.verification["source_before"] == result.verification["source_after"]
    assert result.verification["decoded_base_format"] == "yuv444p"
    assert result.verification["decoded_gain_map_format"] == "gray"
    assert result.verification["hdr_finite"] is True
    assert result.verification["hdr_max"] > 1.0
    assert result.verification["gain_map_present"] is True
    assert result.output.read_bytes()[4:8] == b"ftyp"
    assert source.stat().st_mtime_ns == before.st_mtime_ns
    assert source.stat().st_size == before.st_size

def test_invalid_raw_leaves_no_output_or_temporary_results(tmp_path: Path) -> None:
    source = tmp_path / 'invalid.ARW'
    source.write_bytes(b'not a RAW file')
    output = tmp_path / 'invalid.heic'
    before = source.stat()
    with pytest.raises(rawpy.LibRawError):
        convert_raw(source, output)
    assert not output.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['invalid.ARW']
    assert source.read_bytes() == b'not a RAW file'
    assert source.stat().st_mtime_ns == before.st_mtime_ns

@pytest.mark.real_raw
@pytest.mark.skipif(not os.environ.get('RAWHDR_SAMPLE'), reason='private ARW not configured')
def test_conservative_hdr_keeps_shadows_close_to_sdr(tmp_path: Path) -> None:
    result = convert_raw(Path(os.environ['RAWHDR_SAMPLE']), tmp_path / 'natural.heic')
    assert result.verification is not None
    assert result.verification['shadow_mean_abs_change'] < 0.01
    assert result.verification['hdr_above_sdr_white_pixels'] > 0

@pytest.mark.real_raw
@pytest.mark.skipif(not os.environ.get('RAWHDR_SAMPLE'), reason='private ARW not configured')
def test_comparison_jpeg_is_generated_from_same_raw_intents(tmp_path: Path) -> None:
    jpeg = tmp_path / 'comparison.jpg'
    result = convert_raw(Path(os.environ['RAWHDR_SAMPLE']), tmp_path / 'comparison.heic', comparison_jpeg=jpeg)
    assert result.status == 'success'
    assert jpeg.read_bytes()[:2] == b'\xff\xd8'
    assert result.verification['comparison_jpeg']['ultrahdr_probe'] is True
    assert result.verification['comparison_jpeg']['width'] == result.verification['width']
    assert result.verification['comparison_jpeg']['height'] == result.verification['height']

@pytest.mark.real_raw
@pytest.mark.skipif(not os.environ.get('RAWHDR_COLOR_SAMPLE'), reason='private color reference not configured')
def test_real_raw_does_not_repeat_dark_desaturated_camera_comparison(tmp_path: Path) -> None:
    import subprocess
    import sys
    source = Path(os.environ['RAWHDR_COLOR_SAMPLE'])
    jpeg = tmp_path / 'color.jpg'
    result = convert_raw(source, tmp_path / 'color.heic', comparison_jpeg=jpeg)
    assert result.status == 'success'
    import pillow_heif
    decoded = pillow_heif.open_heif(result.output).to_pillow()
    decoded.load()
    assert decoded.size == (result.verification['width'], result.verification['height'])
    checked = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'scripts/diagnose-color.py'),
                              str(source.with_suffix('.HIF')), str(jpeg)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr
