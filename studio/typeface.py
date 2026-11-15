"""Convert a TrueType font into three.js typeface JSON for extruded 3D text.

``FontLoader`` + ``TextGeometry`` need glyph outlines as typeface JSON. This
reads the ``glyf`` outlines of a .ttf directly (no extra dependency), keeps
only the characters a text object uses, and writes the small JSON the
browser renderer loads. CFF-flavoured .otf fonts have no ``glyf`` table;
``convert`` returns None for them and the renderer falls back to a flat
textured plane.
"""

import struct
from pathlib import Path


class _Font:
    def __init__(self, data):
        self.data = data
        if data[:4] not in (b"\x00\x01\x00\x00", b"true"):
            raise ValueError("not a TrueType font")
        count = struct.unpack(">H", data[4:6])[0]
        self.tables = {}
        for index in range(count):
            tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * index:28 + 16 * index])
            self.tables[tag.decode("latin-1")] = (offset, length)
        if "glyf" not in self.tables:
            raise ValueError("no glyf table")
        head = self.tables["head"][0]
        self.units = struct.unpack(">H", data[head + 18:head + 20])[0]
        self.box = struct.unpack(">hhhh", data[head + 36:head + 44])
        self.long_loca = struct.unpack(">h", data[head + 50:head + 52])[0] == 1
        self.glyph_count = struct.unpack(">H", data[self.tables["maxp"][0] + 4:self.tables["maxp"][0] + 6])[0]
        hhea = self.tables["hhea"][0]
        self.ascender, self.descender = struct.unpack(">hh", data[hhea + 4:hhea + 8])
        self.metrics = struct.unpack(">H", data[hhea + 34:hhea + 36])[0]
        post = self.tables.get("post")
        self.underline = struct.unpack(">hh", data[post[0] + 8:post[0] + 12]) if post else (-100, 50)
        self.cmap = self._cmap()

    def _u16(self, at):
        return struct.unpack(">H", self.data[at:at + 2])[0]

    def _cmap(self):
        base = self.tables["cmap"][0]
        best = None
        for index in range(self._u16(base + 2)):
            platform, encoding, offset = struct.unpack(">HHI", self.data[base + 4 + 8 * index:base + 12 + 8 * index])
            fmt = self._u16(base + offset)
            if (platform, fmt) in ((3, 12), (0, 12)) or (fmt == 12 and best is None):
                best = (fmt, base + offset)
                break
            if fmt == 4 and (platform == 3 or best is None):
                best = (fmt, base + offset)
        if not best:
            return {}
        fmt, at = best
        mapping = {}
        if fmt == 4:
            segments = self._u16(at + 6) // 2
            ends = at + 14
            starts = ends + 2 * segments + 2
            deltas = starts + 2 * segments
            ranges = deltas + 2 * segments
            for seg in range(segments):
                end, start = self._u16(ends + 2 * seg), self._u16(starts + 2 * seg)
                delta, range_offset = self._u16(deltas + 2 * seg), self._u16(ranges + 2 * seg)
                for code in range(start, min(end, 0xFFFE) + 1):
                    if range_offset:
                        glyph = self._u16(ranges + 2 * seg + range_offset + 2 * (code - start))
                        glyph = (glyph + delta) & 0xFFFF if glyph else 0
                    else:
                        glyph = (code + delta) & 0xFFFF
                    mapping[code] = glyph
        else:
            groups = struct.unpack(">I", self.data[at + 12:at + 16])[0]
            for index in range(groups):
                start, end, glyph = struct.unpack(">III", self.data[at + 16 + 12 * index:at + 28 + 12 * index])
                for code in range(start, min(end, start + 0xFFFF) + 1):
                    mapping[code] = glyph + code - start
        return mapping

    def advance(self, glyph):
        hmtx = self.tables["hmtx"][0]
        return self._u16(hmtx + 4 * min(glyph, self.metrics - 1))

    def _glyph_span(self, glyph):
        loca = self.tables["loca"][0]
        if self.long_loca:
            start, end = struct.unpack(">II", self.data[loca + 4 * glyph:loca + 4 * glyph + 8])
        else:
            start, end = (2 * value for value in struct.unpack(">HH", self.data[loca + 2 * glyph:loca + 2 * glyph + 4]))
        return self.tables["glyf"][0] + start, end - start

    def contours(self, glyph, depth=0):
        """Contours as lists of (x, y, on_curve) in font units."""
        if glyph >= self.glyph_count or depth > 8:
            return []
        at, length = self._glyph_span(glyph)
        if length <= 0:
            return []
        data = self.data
        count = struct.unpack(">h", data[at:at + 2])[0]
        cursor = at + 10
        if count >= 0:
            ends = list(struct.unpack(f">{count}H", data[cursor:cursor + 2 * count]))
            cursor += 2 * count
            cursor += 2 + self._u16(cursor)
            total = ends[-1] + 1 if ends else 0
            flags = []
            while len(flags) < total:
                flag = data[cursor]
                cursor += 1
                flags.append(flag)
                if flag & 8:
                    flags.extend([flag] * data[cursor])
                    cursor += 1
            flags = flags[:total]
            coords = []
            for short, same in ((2, 16), (4, 32)):
                value, values = 0, []
                for flag in flags:
                    if flag & short:
                        step = data[cursor]
                        cursor += 1
                        value += step if flag & same else -step
                    elif not flag & same:
                        value += struct.unpack(">h", data[cursor:cursor + 2])[0]
                        cursor += 2
                    values.append(value)
                coords.append(values)
            points = [(x, y, bool(flag & 1)) for x, y, flag in zip(coords[0], coords[1], flags)]
            result, start = [], 0
            for end in ends:
                result.append(points[start:end + 1])
                start = end + 1
            return result
        result = []
        while True:
            flags, index = struct.unpack(">HH", data[cursor:cursor + 4])
            cursor += 4
            if flags & 1:
                dx, dy = struct.unpack(">hh", data[cursor:cursor + 4])
                cursor += 4
            else:
                dx, dy = struct.unpack(">bb", data[cursor:cursor + 2])
                cursor += 2
            a, b, c, d = 1.0, 0.0, 0.0, 1.0
            if flags & 8:
                a = d = struct.unpack(">h", data[cursor:cursor + 2])[0] / 16384
                cursor += 2
            elif flags & 0x40:
                a, d = (value / 16384 for value in struct.unpack(">hh", data[cursor:cursor + 4]))
                cursor += 4
            elif flags & 0x80:
                a, b, c, d = (value / 16384 for value in struct.unpack(">hhhh", data[cursor:cursor + 8]))
                cursor += 8
            if not flags & 2:
                dx = dy = 0  # Point-matched offsets are rare in display fonts; place unshifted.
            for contour in self.contours(index, depth + 1):
                result.append([(a * x + c * y + dx, b * x + d * y + dy, on) for x, y, on in contour])
            if not flags & 0x20:
                return result


def _fmt(value):
    return str(int(round(value)))


def outline(contours):
    """typeface ``o`` string: m/l/q commands (q takes the end point, then the control)."""
    parts = []
    for contour in contours:
        if len(contour) < 2:
            continue
        points = list(contour)
        if not any(on for _, _, on in points):
            (x0, y0, _), (x1, y1, _) = points[0], points[1]
            points.insert(0, ((x0 + x1) / 2, (y0 + y1) / 2, True))
        while not points[0][2]:
            points.append(points.pop(0))
        start = points[0]
        parts += ["m", _fmt(start[0]), _fmt(start[1])]
        control = None
        for x, y, on in points[1:] + [start]:
            if on:
                if control:
                    parts += ["q", _fmt(x), _fmt(y), _fmt(control[0]), _fmt(control[1])]
                else:
                    parts += ["l", _fmt(x), _fmt(y)]
                control = None
            elif control:
                mid = ((control[0] + x) / 2, (control[1] + y) / 2)
                parts += ["q", _fmt(mid[0]), _fmt(mid[1]), _fmt(control[0]), _fmt(control[1])]
                control = (x, y)
            else:
                control = (x, y)
    return " ".join(parts)


def convert(path, text):
    """Typeface JSON dict for the characters in ``text``, or None if the font can't be read."""
    try:
        font = _Font(Path(path).read_bytes())
    except (OSError, ValueError, struct.error, KeyError):
        return None
    glyphs = {}
    for char in sorted(set(text) | {" "}):
        glyph = font.cmap.get(ord(char), 0)
        contours = font.contours(glyph)
        xs = [x for contour in contours for x, _, _ in contour] or [0]
        glyphs[char] = {"ha": font.advance(glyph), "x_min": min(xs), "x_max": max(xs), "o": outline(contours)}
    x_min, y_min, x_max, y_max = font.box
    return {"glyphs": glyphs, "familyName": Path(path).stem, "resolution": font.units,
            "ascender": font.ascender, "descender": font.descender,
            "underlinePosition": font.underline[0], "underlineThickness": font.underline[1],
            "boundingBox": {"xMin": x_min, "yMin": y_min, "xMax": x_max, "yMax": y_max},
            "original_font_information": {}, "cssFontWeight": "normal", "cssFontStyle": "normal"}
