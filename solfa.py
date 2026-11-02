"""Staff notation (any score music21 can read) -> tonic sol-fa data model.

Conventions (Curwen style):
  * Doh is taken from the key signature. Minor keys are "lah-based": doh is the
    tonic of the relative major (A minor -> doh = C), which is the traditional rule.
  * Octave marks: a small number after the syllable, up (d1) or down (s1 below).
  * Separators:  |  bar    :  beat    .  half beat    ,  quarter beat
  * "-" holds a note over a whole beat; a blank beat is a rest.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

from music21 import chord, key, meter, note, stream

# semitones above doh -> syllable (edit these tables if your tradition differs)
NATURAL = {0: "d", 2: "r", 4: "m", 5: "f", 7: "s", 9: "l", 11: "t"}
SHARP = {1: "de", 3: "re", 6: "fe", 8: "se", 10: "le"}
FLAT = {1: "ra", 3: "ma", 6: "sa", 8: "lo", 10: "ta"}


def frac(x) -> Fraction:
    return Fraction(x).limit_denominator(48)


@dataclass
class Cell:
    sep: str            # separator drawn before the cell: "|" ":" "." ","
    text: str = ""      # syllable, "-" (hold) or "" (rest / continuation)
    oct: int = 0        # octave mark: +1 = one octave up, -1 = one octave down
    lyric: str = ""


@dataclass
class Line:
    label: str
    measures: list[list[Cell]]
    has_lyrics: bool = False


@dataclass
class Piece:
    title: str = ""
    composer: str = ""
    key_desc: str = ""
    time_sig: str = ""
    lines: list[Line] = field(default_factory=list)
    annotations: dict[int, str] = field(default_factory=dict)  # measure index -> text
    warnings: list[str] = field(default_factory=list)


@dataclass
class Ev:
    start: Fraction
    end: Fraction
    name: str | None    # None = rest
    oct: int = 0
    hold: bool = False  # tied continuation
    lyric: str = ""


def syllable(p, doh_pc: int) -> tuple[str, int]:
    semi = (p.pitchClass - doh_pc) % 12
    if semi in NATURAL:
        name = NATURAL[semi]
    else:
        alter = p.accidental.alter if p.accidental else 0
        name = SHARP[semi] if alter > 0 else FLAT[semi]
    # unmarked octave = the octave of the doh nearest to middle C
    base = 60 + ((doh_pc + 6) % 12 - 6)
    return name, math.floor((p.ps - base) / 12)


def extract_events(s, shift: Fraction, doh_pc: int, lyrics: bool) -> list[Ev]:
    out: list[Ev] = []
    if s is None:
        return out
    for el in s.notesAndRests:
        if el.duration.isGrace or el.quarterLength == 0:
            continue
        start = frac(el.offset) + shift
        end = start + frac(el.quarterLength)
        if el.isRest:
            out.append(Ev(start, end, None))
            continue
        if not isinstance(el, (note.Note, chord.Chord)):
            continue  # unpitched percussion etc.
        p = max(el.pitches, key=lambda q: q.ps) if el.isChord else el.pitch  # chords: top note
        tied = el.tie is not None and el.tie.type in ("stop", "continue")
        lyr = ""
        if lyrics and el.lyrics and not tied:
            ly = el.lyrics[0]
            lyr = (ly.text or "") + ("-" if ly.syllabic in ("begin", "middle") else "")
        name, octv = syllable(p, doh_pc)
        out.append(Ev(start, end, name, octv, tied, lyr))
    out.sort(key=lambda e: e.start)
    return out


def pick_division(fracs: list[Fraction]) -> int:
    for n in (1, 2, 4, 3, 6, 8, 12):
        if all((f * n).denominator == 1 for f in fracs):
            return n
    return 12


def layout_measure(events: list[Ev], bar: Fraction, beat: Fraction) -> list[Cell]:
    cells: list[Cell] = []
    for b in range(max(1, math.ceil(bar / beat))):
        b0, b1 = beat * b, beat * (b + 1)
        starting = [e for e in events if b0 <= e.start < b1]
        n = pick_division([(e.start - b0) / beat for e in starting])
        step = beat / n
        slot_new: dict[int, Ev] = {}
        for e in starting:
            slot_new[min(n - 1, int(round((e.start - b0) / step)))] = e
        for i in range(n):
            t = b0 + step * i
            e = slot_new.get(i)
            new = e is not None
            if not new:
                e = next((x for x in events if x.start <= t < x.end), None)
            half = n % 2 == 0 and n >= 4 and i == n // 2
            if not (i == 0 or new or half):
                continue  # note simply continues through this sub-division
            if i == 0:
                sep = "|" if b == 0 else ":"
            else:
                sep = "." if (n == 3 or i == n // 2) else ","
            if new:
                if e.name is None:
                    cells.append(Cell(sep))
                elif e.hold:
                    cells.append(Cell(sep, "-"))
                else:
                    cells.append(Cell(sep, e.name, e.oct, e.lyric))
            elif i == 0 and e is not None and e.name is not None:
                cells.append(Cell(sep, "-"))
            else:
                cells.append(Cell(sep))
    return cells


def part_lines(measures: list) -> list[list[tuple]]:
    """Split a part into one or more melodic lines (one per voice id)."""
    vids = sorted({str(v.id) for m in measures for v in m.voices})
    if not vids:
        return [[(m, m) for m in measures]]
    lines = []
    for vid in vids:
        line = []
        for m in measures:
            if m.voices:
                line.append((m, next((v for v in m.voices if str(v.id) == vid), None)))
            else:
                line.append((m, m if vid == vids[0] else None))
        lines.append(line)
    return lines


def _ctx(m, cls):
    """Nearest element of `cls` at or before measure m (m.getContextByClass misses
    elements that sit inside m itself, e.g. the key signature of bar 1)."""
    inside = m.getElementsByClass(cls).first()
    return inside if inside is not None else m.getContextByClass(cls)


def _pname(p) -> str:
    return p.name.replace("-", "b")


def convert_score(sc, lyrics: bool = True) -> Piece:
    if isinstance(sc, stream.Opus):
        sc = sc.scores[0]
    parts = list(sc.parts) if isinstance(sc, stream.Score) else []
    if not parts:
        parts = [sc]

    piece = Piece()
    md = getattr(sc, "metadata", None)
    if md is not None:
        piece.title = md.title or md.movementName or ""
        piece.composer = "" if (md.composer or "") == "Music21" else (md.composer or "")

    bad: set = set()
    for pi, part in enumerate(parts):
        measures = list(part.getElementsByClass(stream.Measure))
        if not measures:
            part = part.makeMeasures()
            measures = list(part.getElementsByClass(stream.Measure))
        if not measures:
            continue
        base = (getattr(part, "partName", None) or f"P{pi + 1}")[:5]
        vlines = part_lines(measures)
        for vi, vline in enumerate(vlines):
            cells_per_measure: list[list[Cell]] = []
            has_lyr = False
            prev_sharps = prev_ts = None
            for idx, (m, s) in enumerate(vline):
                ks = _ctx(m, key.KeySignature)
                sharps = ks.sharps if ks is not None else 0
                ts = _ctx(m, meter.TimeSignature) or meter.TimeSignature("4/4")
                bar = frac(ts.barDuration.quarterLength)
                try:
                    beat = frac(ts.beatDuration.quarterLength)
                except Exception:
                    beat = Fraction(1)
                doh = key.KeySignature(sharps).asKey("major").tonic
                hl = frac(m.highestTime)
                shift = Fraction(0)
                if idx == 0 and m.paddingLeft:
                    shift = frac(m.paddingLeft)          # pick-up bar flagged by the file
                elif idx == 0 and 0 < hl < bar:
                    shift = bar - hl                     # pick-up bar: right-align
                elif 0 < idx < len(vline) - 1 and hl != bar:
                    bad.add(m.number)
                ev = extract_events(s, shift, doh.pitchClass, lyrics)
                cells = layout_measure(ev, bar, beat)
                has_lyr = has_lyr or any(c.lyric for c in cells)
                cells_per_measure.append(cells)
                if pi == 0 and vi == 0:
                    if idx == 0:
                        lah = key.KeySignature(sharps).asKey("major").relative.tonic
                        piece.key_desc = f"Doh is {_pname(doh)}  (minor keys: lah is {_pname(lah)})"
                        piece.time_sig = ts.ratioString
                    else:
                        note_txt = []
                        if sharps != prev_sharps:
                            note_txt.append(f"Doh = {_pname(doh)}")
                        if ts.ratioString != prev_ts:
                            note_txt.append(ts.ratioString)
                        if note_txt:
                            piece.annotations[idx] = "  ".join(note_txt)
                prev_sharps, prev_ts = sharps, ts.ratioString
            label = base if len(vlines) == 1 else f"{base[:4]}{vi + 1}"
            piece.lines.append(Line(label, cells_per_measure, has_lyr))

    if not piece.lines:
        raise ValueError("No notes were found in the score.")
    if len(piece.lines) == 4:  # SATB hymn (4 parts, or 2 staves x 2 voices)
        for line, name in zip(piece.lines, "SATB"):
            line.label = name
    if bad:
        shown = ", ".join(str(n) for n in sorted(bad)[:12])
        piece.warnings.append(
            f"{len(bad)} bar(s) don't add up to the time signature (e.g. bar {shown}). "
            "This usually means the music was misread - check against the original."
        )
    return piece
