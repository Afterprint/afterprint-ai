FROM python:3.13-slim

# System dependencies: FFmpeg for audio/video, Tesseract for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ ./src/

# Non-root user
RUN addgroup --system afterprint && adduser --system --ingroup afterprint afterprint
USER afterprint

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "afterprint_ai.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
