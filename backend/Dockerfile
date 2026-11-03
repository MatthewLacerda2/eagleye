FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ffmpeg grabs frames from camera feeds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first so the dependency layer is cached across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application package.
COPY . .

# Drop root only after the dependencies are installed system-wide.
# Port 8000 is unprivileged, so uvicorn needs nothing beyond this.
# /data/frames is created here so the named volume inherits app's ownership.
RUN useradd --create-home --uid 1001 app \
    && mkdir -p /data/frames \
    && chown -R app:app /app /data
USER app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
