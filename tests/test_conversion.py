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
