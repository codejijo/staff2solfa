from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from pipeline import SCORE_EXTS, PipelineError, process

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
JOB_TTL_SECONDS = 60 * 60
WORKERS = int(os.environ.get("OMR_WORKERS", "2"))  # Audiveris is memory hungry

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
log = logging.getLogger("solfa")

ROOT = Path(tempfile.gettempdir()) / "solfa-jobs"
ROOT.mkdir(exist_ok=True)
pool = ThreadPoolExecutor(max_workers=WORKERS)
jobs: dict[str, dict] = {}
lock = threading.Lock()
ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _cleanup() -> None:
    now = time.time()
    with lock:
        old = [i for i, j in jobs.items() if now - j["created"] > JOB_TTL_SECONDS]
        for i in old:
            jobs.pop(i, None)
    for i in old:
        shutil.rmtree(ROOT / i, ignore_errors=True)


def _run(job_id: str, src: Path, lyrics: bool, paper: str) -> None:
    with lock:
        jobs[job_id]["status"] = "running"
        hint = jobs[job_id]["name"]
    try:
        pdf, info = process(src, ROOT / job_id, lyrics=lyrics, paper=paper, title_hint=hint)
        with lock:
            jobs[job_id].update(status="done", result=str(pdf), info=info)
    except PipelineError as e:
        with lock:
            jobs[job_id].update(status="error", error=str(e))
    except Exception:
        log.exception("job %s failed", job_id)
        with lock:
            jobs[job_id].update(status="error", error="Something went wrong while converting this file.")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/api/jobs")
def create_job():
    _cleanup()
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify(error="Choose a file to upload."), 400
    ext = Path(f.filename).suffix.lower()
    if ext != ".pdf" and ext not in SCORE_EXTS:
        return jsonify(error="Upload a PDF (MusicXML and MIDI also work)."), 400
    job_id = uuid.uuid4().hex
    work = ROOT / job_id
    work.mkdir(parents=True)
    src = work / f"input{ext}"
    f.save(src)
    if ext == ".pdf" and src.read_bytes()[:5] != b"%PDF-":
        shutil.rmtree(work, ignore_errors=True)
        return jsonify(error="That file isn't a valid PDF."), 400
    lyrics = request.form.get("lyrics", "1") == "1"
    paper = "letter" if request.form.get("paper") == "letter" else "a4"
    with lock:
        jobs[job_id] = {"status": "queued", "created": time.time(),
                        "name": Path(f.filename).stem[:80] or "score"}
    pool.submit(_run, job_id, src, lyrics, paper)
    return jsonify(id=job_id), 202


@app.get("/api/jobs/<job_id>")
def job_status(job_id: str):
    if not ID_RE.match(job_id):
        abort(404)
    with lock:
        j = jobs.get(job_id)
        if j is None:
            abort(404)
        return jsonify(status=j["status"], error=j.get("error"), info=j.get("info"))


@app.get("/api/jobs/<job_id>/download")
def download(job_id: str):
    if not ID_RE.match(job_id):
        abort(404)
    with lock:
        j = jobs.get(job_id)
        if j is None or j["status"] != "done":
            abort(404)
        path, name = j["result"], j["name"]
    return send_file(path, as_attachment=True, download_name=f"{name}-solfa.pdf",
                     mimetype="application/pdf")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
