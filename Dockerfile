# Use Python base image (Debian 12 "bookworm")
FROM python:3.12-slim-bookworm

# Install Chromium + matching Chromedriver from Debian packages.
# Both come from the same package source, so their versions always match and
# Selenium does not have to download a driver at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# PYTHONUNBUFFERED: print() output shows up immediately in the Render/Railway logs
# CHROME_BIN / CHROMEDRIVER_PATH: used by chrome_driver.py
# LOW_MEMORY: enables the memory-saving Chrome flags (Render Free = 512 MB RAM)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    LOW_MEMORY=1

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Render sets $PORT (default 10000), Railway sets it dynamically
EXPOSE 10000

# Single worker: search status is kept in memory
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1"]
