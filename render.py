"""Render Piece objects to a PDF using only ReportLab built-in fonts.

Octave marks are drawn as small raised/lowered numbers (not Unicode sub/superscripts,
which the built-in fonts cannot show).
"""
from __future__ import annotations

from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from solfa import Cell, Piece

FONT = "Courier"
MARK_SCALE = 0.62
FOOTER = "Automatically converted from staff notation - proofread against the original before use."


def cell_chars(c: Cell) -> float:
    body = len(c.text) + (MARK_SCALE if c.oct and c.text else 0)
    return len(c.sep) + max(body, len(c.lyric), 1) + 1


def render_pdf(pieces: list[Piece], out_path, paper: str = "a4", fs: float = 11.0) -> None:
    W, H = A4 if paper.lower() == "a4" else letter
    M = 42
    c = canvas.Canvas(str(out_path), pagesize=(W, H))
    cw = pdfmetrics.stringWidth("M", FONT, fs)
    label_chars = 7
    x0 = M + label_chars * cw
    usable = W - M - x0 - 3 * cw  # leave room for the closing double bar

    def footer():
        c.setFont("Helvetica", 7)
        c.setFillGray(0.45)
        c.drawString(M, M - 20, FOOTER)
        c.setFillGray(0)

    y = H - M
    first_page = True

    def new_page():
        nonlocal y
        footer()
        c.showPage()
        y = H - M

    for pi, piece in enumerate(pieces):
        if pi > 0:
            new_page()
        first_page = False

        # ---- header
        c.setFont("Helvetica-Bold", 17)
        c.drawString(M, y - 14, piece.title or "Untitled")
        y -= 20
        if piece.composer:
            c.setFont("Helvetica", 10)
            c.drawRightString(W - M, y, piece.composer)
        c.setFont("Helvetica", 10)
        c.drawString(M, y - 6, f"{piece.key_desc}      Time: {piece.time_sig}")
        y -= 26

        # ---- column widths: each bar is as wide as its widest part, so barlines line up
        nm = max(len(l.measures) for l in piece.lines)
        widths = []
        for mi in range(nm):
            w = 0.0
            for l in piece.lines:
                cells = l.measures[mi] if mi < len(l.measures) else []
                w = max(w, sum(cell_chars(ce) for ce in cells))
            widths.append(max(w, 4.0))

        systems, cur, cur_w = [], [], 0.0
        for mi, w in enumerate(widths):
            if cur and (cur_w + w) * cw > usable:
                systems.append(cur)
                cur, cur_w = [], 0.0
            cur.append(mi)
            cur_w += w
        if cur:
            systems.append(cur)

        for sysm in systems:
            ann_h = fs * 1.4 if any(mi in piece.annotations for mi in sysm) else 0
            rows_h = sum(fs * (2.5 if l.has_lyrics else 1.6) for l in piece.lines)
            if y - (ann_h + rows_h) < M + 10:
                new_page()
            y -= ann_h
            ry = y
            for line in piece.lines:
                ry -= fs
                c.setFont(FONT, fs)
                c.drawString(M, ry, line.label)
                x = x0
                for mi in sysm:
                    mx = x
                    cells = line.measures[mi] if mi < len(line.measures) else []
                    for ce in cells:
                        c.setFont(FONT, fs)
                        c.drawString(mx, ry, ce.sep + ce.text)
                        tx = mx + (len(ce.sep) + len(ce.text)) * cw
                        if ce.oct and ce.text:
                            c.setFont(FONT, fs * MARK_SCALE)
                            dy = fs * 0.42 if ce.oct > 0 else -fs * 0.22
                            c.drawString(tx, ry + dy, str(abs(ce.oct)))
                        if ce.lyric:
                            c.setFont(FONT, fs * 0.9)
                            c.drawString(mx + len(ce.sep) * cw, ry - fs * 1.05, ce.lyric)
                        mx += cell_chars(ce) * cw
                    if mi == nm - 1:
                        c.setFont(FONT, fs)
                        c.drawString(x + widths[mi] * cw, ry, "||")
                    x += widths[mi] * cw
                ry -= fs * (1.5 if line.has_lyrics else 0.6)
            if ann_h:
                ax = x0
                c.setFont("Helvetica-Oblique", 8.5)
                for mi in sysm:
                    if mi in piece.annotations:
                        c.drawString(ax, y + fs * 0.3, piece.annotations[mi])
                    ax += widths[mi] * cw
            y = ry - fs * 0.9

        if piece.warnings:
            c.setFont("Helvetica-Oblique", 8.5)
            for wmsg in piece.warnings:
                if y < M + 20:
                    new_page()
                c.drawString(M, y - 10, "Note: " + wmsg[:150])
                y -= 12

    footer()
    c.save()
