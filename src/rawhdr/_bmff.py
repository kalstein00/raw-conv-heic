"""Read the bounded hvc1/tmap subset emitted by the pinned PoC encoder.

No libheif/libultrahdr parser or decoder is called here. Unsupported structures
fail closed instead of being reported as verified.
"""

from dataclasses import dataclass
from pathlib import Path


class VerificationError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, size: int) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise VerificationError("Truncated HEIF structure")
        result = self.data[self.pos : self.pos + size]
        self.pos += size
        return result

    def number(self, size: int, *, signed: bool = False) -> int:
        return int.from_bytes(self.take(size), "big", signed=signed)


@dataclass(frozen=True)
class Box:
    kind: bytes
    payload: bytes


def boxes(data: bytes) -> list[Box]:
    result = []
    r = Reader(data)
    while r.pos < len(data):
        size, kind = r.number(4), r.take(4)
        header = 8
        if size == 1:
            size, header = r.number(8), 16
        elif size == 0:
            size = len(data) - r.pos + header
        if size < header:
            raise VerificationError("Invalid box size")
        result.append(Box(kind, r.take(size - header)))
    return result


def one(items: list[Box], kind: bytes) -> bytes:
    found = [box.payload for box in items if box.kind == kind]
    if len(found) != 1:
        raise VerificationError(f"Expected one {kind!r} box, found {len(found)}")
    return found[0]


@dataclass
class HeifFile:
    primary: int
    types: dict[int, bytes]
    items: dict[int, bytes]
    properties: dict[int, list[Box]]
    references: dict[int, list[int]]
    alternatives: list[list[int]]

    def dimensions(self, item: int) -> tuple[int, int]:
        r = Reader(one(self.properties[item], b"ispe"))
        r.take(4)
        width, height = r.number(4), r.number(4)
        if not (0 < width <= 8192 and 0 < height <= 8192):
            raise VerificationError("Unsupported image dimensions")
        return width, height

    def bit_depths(self, item: int) -> list[int]:
        r = Reader(one(self.properties[item], b"pixi"))
        r.take(4)
        return list(r.take(r.number(1)))

    def nclx(self, item: int) -> tuple[int, int, int, bool]:
        profiles = [p.payload for p in self.properties[item] if p.kind == b"colr" and p.payload[:4] == b"nclx"]
        if len(profiles) != 1:
            raise VerificationError("Missing or ambiguous NCLX color profile")
        r = Reader(profiles[0][4:])
        return r.number(2), r.number(2), r.number(2), bool(r.number(1) & 128)

    def annex_b(self, item: int) -> bytes:
        if self.types[item] != b"hvc1":
            raise VerificationError("Verifier only supports directly coded HEVC items")
        r = Reader(one(self.properties[item], b"hvcC"))
        header = r.take(23)
        if header[0] != 1:
            raise VerificationError("Unsupported HEVC configuration version")
        length_size = (header[21] & 3) + 1
        output = bytearray()
        for _ in range(header[22]):
            r.take(1)
            for _ in range(r.number(2)):
                output += b"\x00\x00\x00\x01" + r.take(r.number(2))
        data = Reader(self.items[item])
        while data.pos < len(data.data):
            nal = data.take(data.number(length_size))
            if not nal:
                raise VerificationError("Empty HEVC NAL unit")
            output += b"\x00\x00\x00\x01" + nal
        return bytes(output)


def read_heif(path: Path) -> HeifFile:
    if path.stat().st_size > 512 * 1024 * 1024:
        raise VerificationError("File exceeds the PoC verifier limit")
    data = path.read_bytes()
    top = boxes(data)
    ftyp = one(top, b"ftyp")
    if len(ftyp) < 8 or len(ftyp) % 4:
        raise VerificationError("Malformed file type")
    brands = [ftyp[:4]] + [ftyp[i : i + 4] for i in range(8, len(ftyp), 4)]
    if b"tmap" not in brands or not ({b"heic", b"heix", b"mif1"} & set(brands)):
        raise VerificationError("Not a tone-map HEIF container")
    meta = one(top, b"meta")
    if meta[:4] != b"\0\0\0\0":
        raise VerificationError("Unsupported HEIF meta version")
    children = boxes(meta[4:])
    r = Reader(one(children, b"pitm"))
    version = r.number(1)
    r.take(3)
    primary = r.number(2 if version == 0 else 4)

    r = Reader(one(children, b"iinf"))
    version = r.number(1)
    r.take(3)
    count = r.number(2 if version == 0 else 4)
    info = boxes(r.take(len(r.data) - r.pos))
    if len(info) != count:
        raise VerificationError("Item count mismatch")
    types: dict[int, bytes] = {}
    for box in info:
        r = Reader(box.payload)
        version = r.number(1)
        r.take(3)
        if box.kind != b"infe" or version not in (2, 3):
            raise VerificationError("Unsupported item information")
        item = r.number(2 if version == 2 else 4)
        if r.number(2) or item in types:
            raise VerificationError("Protected or duplicate item")
        types[item] = r.take(4)

    iprp = boxes(one(children, b"iprp"))
    ipco = boxes(one(iprp, b"ipco"))
    r = Reader(one(iprp, b"ipma"))
    version, flags = r.number(1), r.number(3)
    properties: dict[int, list[Box]] = {}
    for _ in range(r.number(4)):
        item = r.number(2 if version == 0 else 4)
        properties[item] = []
        for _ in range(r.number(1)):
            association = r.number(2 if flags & 1 else 1)
            essential = bool(association & (0x8000 if flags & 1 else 0x80))
            index = association & (0x7FFF if flags & 1 else 0x7F)
            if not 0 <= index <= len(ipco):
                raise VerificationError("Property index outside table")
            if essential and (not index or ipco[index - 1].kind not in
                              (b"hvcC", b"ispe", b"pixi", b"colr", b"irot", b"imir", b"clap")):
                raise VerificationError("Unsupported essential image property")
            if index:
                properties[item].append(ipco[index - 1])

    r = Reader(one(children, b"iloc"))
    version = r.number(1)
    if version not in (0, 1, 2):
        raise VerificationError("Unsupported item-location version")
    r.take(3)
    sizes, sizes2 = r.number(1), r.number(1)
    offset_size, length_size = sizes >> 4, sizes & 15
    base_size, index_size = sizes2 >> 4, sizes2 & 15 if version else 0
    if any(size not in (0, 4, 8) for size in (offset_size, length_size, base_size, index_size)):
        raise VerificationError("Unsupported extent size")
    items: dict[int, bytes] = {}
    for _ in range(r.number(2 if version < 2 else 4)):
        item = r.number(2 if version < 2 else 4)
        method = r.number(2) & 15 if version else 0
        if r.number(2) != 0 or method not in (0, 1):
            raise VerificationError("External or unsupported item data")
        origin = data if method == 0 else one(children, b"idat")
        base = r.number(base_size)
        extents = []
        for _ in range(r.number(2)):
            r.take(index_size)
            offset, length = base + r.number(offset_size), r.number(length_size)
            if not length or offset + length > len(origin):
                raise VerificationError("Item extent outside file")
            extents.append(origin[offset : offset + length])
        if item in items:
            raise VerificationError("Duplicate item location")
        items[item] = b"".join(extents)

    refs = one(children, b"iref")
    if refs[0] not in (0, 1):
        raise VerificationError("Unsupported item-reference version")
    references = {}
    for box in boxes(refs[4:]):
        if box.kind == b"dimg":
            r = Reader(box.payload)
            item = r.number(2 if refs[0] == 0 else 4)
            if item in references:
                raise VerificationError("Duplicate derived-image reference")
            references[item] = [r.number(2 if refs[0] == 0 else 4) for _ in range(r.number(2))]
    alternatives = []
    for box in boxes(one(children, b"grpl")):
        if box.kind == b"altr":
            r = Reader(box.payload)
            r.take(8)
            alternatives.append([r.number(4) for _ in range(r.number(4))])
    return HeifFile(primary, types, items, properties, references, alternatives)
