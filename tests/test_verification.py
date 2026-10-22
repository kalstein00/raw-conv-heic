import os
from pathlib import Path
import shutil
import pytest
from rawhdr import verify_heic


@pytest.mark.real_raw
@pytest.mark.skipif(not os.environ.get('RAWHDR_HEIC'), reason='verified local HEIC not configured')
def test_independent_verification_is_read_only_and_rejects_missing_tone_map(tmp_path: Path) -> None:
    sample = tmp_path / 'sample.heic'
    shutil.copyfile(os.environ['RAWHDR_HEIC'], sample)
    before = sample.read_bytes()
    report = verify_heic(sample)
    assert report['hdr_above_sdr_white_pixels'] > 0
    assert sample.read_bytes() == before
    assert list(tmp_path.iterdir()) == [sample]
    sample.write_bytes(before.replace(b'tmap', b'xxxx'))
    with pytest.raises(ValueError):
        verify_heic(sample)

# Build altered containers around real encoded payloads. Relocating the meta
# box preserves original absolute iloc offsets, without using the product parser.
def _box(kind: bytes, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, 'big') + kind + payload


def _chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    result = []
    offset = 0
    while offset < len(data):
        size = int.from_bytes(data[offset:offset + 4], 'big')
        assert 8 <= size <= len(data) - offset
        result.append((data[offset + 4:offset + 8], data[offset + 8:offset + size]))
        offset += size
    return result


def _with_property(data: bytes, item: int, kind: bytes, payload: bytes, essential: bool) -> bytes:
    top = _chunks(data)
    meta = next(payload for kind, payload in top if kind == b'meta')
    children = _chunks(meta[4:])
    iprp = _chunks(next(payload for kind, payload in children if kind == b'iprp'))
    ipco = next(payload for kind, payload in iprp if kind == b'ipco')
    index = len(_chunks(ipco)) + 1
    assert index < 128
    ipma = next(payload for kind, payload in iprp if kind == b'ipma')
    assert ipma[:4] == b'\0\0\0\0'  # fixture's 16-bit IDs / 8-bit associations
    updated = bytearray(ipma[:8])
    cursor = 8
    for _ in range(int.from_bytes(ipma[4:8], 'big')):
        identifier = int.from_bytes(ipma[cursor:cursor + 2], 'big')
        count = ipma[cursor + 2]
        associations = ipma[cursor + 3:cursor + 3 + count]
        if identifier == item:
            associations += bytes([index | (128 if essential else 0)])
        updated += identifier.to_bytes(2, 'big') + bytes([len(associations)]) + associations
        cursor += 3 + count
    replacement = b''.join(_box(k, ipco + _box(kind, payload) if k == b'ipco' else bytes(updated) if k == b'ipma' else v)
                           for k, v in iprp)
    new_meta = meta[:4] + b''.join(_box(k, replacement if k == b'iprp' else v) for k, v in children)
    return b''.join(_box(b'free' if k == b'meta' else k, v) for k, v in top) + _box(b'meta', new_meta)


@pytest.mark.real_raw
@pytest.mark.skipif(not os.environ.get('RAWHDR_HEIC'), reason='verified local HEIC not configured')
@pytest.mark.parametrize('item', [2, 3])
@pytest.mark.parametrize('kind,payload', [(b'irot', b'\x01'), (b'imir', b'\x00'), (b'clap', b'\0' * 32)])
def test_unsupported_gain_map_rotation_is_not_claimed_verified(tmp_path: Path, item: int, kind: bytes, payload: bytes) -> None:
    sample = tmp_path / 'rotated-gain.heic'
    data = Path(os.environ['RAWHDR_HEIC']).read_bytes()
    sample.write_bytes(_with_property(data, item, kind, payload, False))
    with pytest.raises(ValueError, match='oriented and cropped'):
        verify_heic(sample)


@pytest.mark.real_raw
@pytest.mark.skipif(not os.environ.get('RAWHDR_HEIC'), reason='verified local HEIC not configured')
def test_unknown_essential_property_is_not_ignored(tmp_path: Path) -> None:
    sample = tmp_path / 'unknown-essential.heic'
    data = Path(os.environ['RAWHDR_HEIC']).read_bytes()
    sample.write_bytes(_with_property(data, 3, b'zzzz', b'\x01', True))
    with pytest.raises(ValueError, match='essential'):
        verify_heic(sample)
