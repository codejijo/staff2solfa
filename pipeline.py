"""PDF (or MusicXML/MIDI) in, tonic sol-fa PDF out."""
from __future__ import annotations

import logging
import math
import os
import re
import subprocess
from pathlib import Path

from music21 import converter
from pypdf import PdfReader, PdfWriter

from render import render_pdf
from solfa import convert_score

SCORE_EXTS = {".musicxml", ".xml", ".mxl", ".mid", ".midi"}
log = logging.getLogger("solfa")

# Audiveris refuses pages that render to more than ~20 million pixels. Digital PDFs with a
# huge page size (poster-sized exports, custom page settings) trip this, so we shrink pages
# that are much bigger than A4 before recognition. Vector music loses nothing by this.
A4_AREA = 595.0 * 842.0
MAX_PAGE_AREA = A4_AREA * 1.15
TOO_LARGE = re.compile(r"Too large image:\s*([\d,]+)\s*pixels\s*\(vs\s*([\d,]+)", re.I)


class PipelineError(Exception):
    """Raised with a message that is safe to show to the user."""


def shrink_pdf(src: Path, dst: Path, factor: float | None = None) -> bool:
    """Scale pages down and write dst. factor=None: only pages larger than ~A4 are shrunk,
    to A4 area. Returns True if dst was written."""
    try:
        reader = PdfReader(str(src))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PipelineError("This PDF is password protected. Remove the password and try again.")
        writer = PdfWriter()
        changed = False
        for page in reader.pages:
            w, h = float(page.mediabox.width), float(page.mediabox.height)
            log.info("PDF page size: %.0f x %.0f pt (%.0f x %.0f mm)", w, h, w / 72 * 25.4, h / 72 * 25.4)
            f = factor if factor else (math.sqrt(MAX_PAGE_AREA / (w * h)) if w * h > MAX_PAGE_AREA else 1.0)
            if f < 0.999:
                page.scale_by(f)
                changed = True
            writer.add_page(page)
        if changed:
            with open(dst, "wb") as fh:
                writer.write(fh)
        return changed
    except PipelineError:
        raise
    except Exception as e:
        log.warning("Could not resize PDF (%s); using it as is", e)
        return False


def _audiveris(pdf: Path, out_dir: Path, timeout: int) -> tuple[list[Path], str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        os.environ.get("AUDIVERIS_CMD", "audiveris"),
        "-batch", "-transcribe", "-export",
        "-output", str(out_dir), str(pdf),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise PipelineError("The music recognition engine (Audiveris) is not installed on the server.")
    except subprocess.TimeoutExpired:
        raise PipelineError("Recognition took too long. Try a shorter score or fewer pages.")
    files = sorted(p for p in out_dir.rglob("*") if p.suffix.lower() in {".mxl", ".musicxml"})
    return files, (proc.stdout or "") + "\n" + (proc.stderr or "")


def run_audiveris(pdf: Path, out_dir: Path, timeout: int = 900) -> list[Path]:
    current = pdf
    fitted = pdf.with_name("fitted.pdf")
    if shrink_pdf(pdf, fitted):
        current = fitted
    files, output = _audiveris(current, out_dir, timeout)

    m = TOO_LARGE.search(output) if not files else None
    if m:  # still too big: shrink by exactly what the engine asked for, then retry once
        pixels, limit = (int(g.replace(",", "")) for g in m.groups())
        factor = math.sqrt(limit * 0.5 / pixels)
        retry = pdf.with_name("fitted2.pdf")
        if shrink_pdf(current, retry, factor=factor):
            files, output = _audiveris(retry, out_dir, timeout)
            m = TOO_LARGE.search(output) if not files else None

    if not files:
        if m:
            raise PipelineError(
                "The pages in this PDF are too large for the recognition engine, even after shrinking. "
                "Re-export it from your notation software with a standard page size (A4 or Letter)."
            )
        tail = output.strip()[-500:]
        raise PipelineError(
            "No music could be recognised in this PDF. It may be a low-quality scan or not "
            f"printed staff notation.\n\nEngine output:\n{tail}"
        )
    return files


def process(src: Path, work: Path, lyrics: bool = True, paper: str = "a4",
            title_hint: str = "") -> tuple[Path, dict]:
    work.mkdir(parents=True, exist_ok=True)
    ext = src.suffix.lower()
    if ext == ".pdf":
        files = run_audiveris(src, work / "omr")
    elif ext in SCORE_EXTS:
        files = [src]
    else:
        raise PipelineError("Unsupported file type. Upload a PDF (or MusicXML / MIDI).")

    pieces = []
    for f in files:
        try:
            sc = converter.parse(str(f))
            piece = convert_score(sc, lyrics=lyrics)
            piece.title = piece.title or title_hint
            pieces.append(piece)
        except PipelineError:
            raise
        except Exception as e:  # music21 raises many different exception types
            raise PipelineError(f"The recognised score could not be converted: {e}")

    out = work / "solfa.pdf"
    render_pdf(pieces, out, paper=paper)
    info = {
        "parts": sum(len(p.lines) for p in pieces),
        "measures": max(len(l.measures) for p in pieces for l in p.lines),
        "warnings": [w for p in pieces for w in p.warnings],
        "title": pieces[0].title,
    }
    return out, info
