"""Write sample.musicxml: a short two-part piece in G major with a pick-up bar, lyrics,
a tie, a dotted rhythm, a rest and a chromatic note. Upload it to the app (or run
`python tools/make_sample.py && python -c ...`) to test without Audiveris."""
import sys

from music21 import key, meter, metadata, note, stream


def n(p, ql, lyric=None):
    x = note.Note(p, quarterLength=ql)
    if lyric:
        x.addLyric(lyric)
    return x


def build():
    sc = stream.Score()
    sc.metadata = metadata.Metadata(title="Sample Hymn", composer="Test Composer")

    s, b = stream.Part(id="S"), stream.Part(id="B")
    s.partName, b.partName = "Soprano", "Bass"
    sop = [
        [n("D4", 1, "Come")],
        [n("G4", 1, "Glo-"), n("G4", 1, "ry"), n("A4", 1, "to"), n("B4", 1, "God")],
        [n("B4", 1.5, "in"), n("A4", 0.5, "the"), n("G4", 1, "high-"), n("F#4", 1, "est")],
        [n("G4", 1, "Praise"), n("C#5", 1, "Him"), n("D5", 2, "all")],
        [n("B4", 2, "who"), note.Rest(quarterLength=1), n("A4", 0.5, "live"), n("G4", 0.5, "and")],
        [n("G4", 4, "breathe")],
    ]
    bas = [
        [note.Rest(quarterLength=1)],
        [n("G3", 2), n("D3", 2)],
        [n("G3", 2), n("D3", 2)],
        [n("E3", 2), n("D3", 2)],
        [n("G3", 2), n("D3", 2)],
        [n("G2", 4)],
    ]
    for part, rows in ((s, sop), (b, bas)):
        for i, row in enumerate(rows):
            m = stream.Measure(number=i)
            if i == 0:
                m.insert(0, key.KeySignature(1))
                m.insert(0, meter.TimeSignature("4/4"))
            for el in row:
                m.append(el)
            part.append(m)
        part.getElementsByClass(stream.Measure).first().padAsAnacrusis()
        sc.insert(0, part)
    return sc


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample.musicxml"
    build().write("musicxml", fp=out)
    print("wrote", out)
