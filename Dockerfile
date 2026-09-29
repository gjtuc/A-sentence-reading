# Cloud Run / local container — A-sentence-reading gatekeeper
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        ffmpeg \
        espeak-ng \
    && rm -rf /var/lib/apt/lists/*
# design/371 — `espeak-ng` is back, and not because anything reads a dictionary
# again. `Wav2Vec2Processor.from_pretrained` for this model builds a
# `Wav2Vec2PhonemeCTCTokenizer`, whose constructor builds an eSpeak backend for
# the text-to-phoneme direction we never call. Without the binary it raises
# `espeak not installed on your system`, which fails the model prefetch below
# and would leave the waveform pass dead at `load_failed` on every take.
# design/368 removed this line and never rebuilt the image, so nothing broke
# live; the next build would have. Removing it for real means decoding from
# `vocab.json` instead of the tokenizer — see `scripts/ctc_reference_probe.py`.

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install . \
    && pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install transformers==4.46.3 phonemizer==3.3.0

ENV HF_HOME=/opt/hf \
    TRANSFORMERS_OFFLINE=0
RUN python -c "from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor; n='facebook/wav2vec2-lv-60-espeak-cv-ft'; Wav2Vec2Processor.from_pretrained(n); Wav2Vec2ForCTC.from_pretrained(n)"

# Cloud Run injects PORT; ASR_SERVICE_ROLE=worker → ingest worker (design/173c).
EXPOSE 8080
CMD ["sh", "-c", "if [ \"${ASR_SERVICE_ROLE:-api}\" = worker ]; then uvicorn sentence_reading.worker.app:app --host 0.0.0.0 --port ${PORT}; else uvicorn sentence_reading.api.app:app --host 0.0.0.0 --port ${PORT}; fi"]
