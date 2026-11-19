# The Playwright image already has Chromium for the optional browser fallback.
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY aioredgif ./aioredgif
RUN pip install --no-cache-dir ".[browser]"
ENV AIOREDGIF_DOWNLOAD_DIR=/app/downloads
VOLUME /app/downloads
EXPOSE 8000
CMD ["aioredgif", "--host", "0.0.0.0", "--port", "8000"]
