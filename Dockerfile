# Build:  docker build --build-arg AUDIVERIS_DEB_URL=<url of the Ubuntu .deb from
#         https://github.com/Audiveris/audiveris/releases> -t solfa .
# Run:    docker run -p 5000:5000 solfa
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv wget ca-certificates \
      tesseract-ocr tesseract-ocr-eng libfreetype6 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

ARG AUDIVERIS_DEB_URL
RUN test -n "$AUDIVERIS_DEB_URL" && wget -q -O /tmp/audiveris.deb "$AUDIVERIS_DEB_URL" \
    && apt-get update && apt-get install -y /tmp/audiveris.deb \
    && rm -rf /var/lib/apt/lists/* /tmp/audiveris.deb
ENV AUDIVERIS_CMD=/opt/audiveris/bin/Audiveris

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PATH="/venv/bin:$PATH" OMR_WORKERS=2 MAX_UPLOAD_MB=25
EXPOSE 5000
# one process, several threads: job state lives in memory (see README for scaling notes)
CMD ["gunicorn", "-w", "1", "--threads", "8", "--timeout", "1200", "-b", "0.0.0.0:5000", "app:app"]
