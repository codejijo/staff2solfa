# Staff to Sol-fa

PDF (printed staff notation) -> Audiveris OMR -> MusicXML -> tonic sol-fa -> PDF.

## Run locally
    pip install -r requirements.txt
    # install Audiveris (https://github.com/Audiveris/audiveris) and set:
    export AUDIVERIS_CMD=/opt/audiveris/bin/Audiveris
    python app.py            # http://localhost:5000

## Test without Audiveris
    python tools/make_sample.py sample.musicxml
Upload `sample.musicxml` in the UI. MusicXML, .mxl and MIDI skip the recognition step.

## Where to change things
- `solfa.py`   syllable tables, doh/lah rules, rhythm layout (separators, holds)
- `render.py`  PDF look and page layout
- `pipeline.py` Audiveris call
- `app.py`     upload limits, job queue, cleanup
