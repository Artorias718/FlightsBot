FROM python:3.11-slim

WORKDIR /app

# log visibili subito con docker logs, senza buffering di Python
ENV PYTHONUNBUFFERED=1

# dipendenze di sistema per Playwright
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# install browser chromium di playwright
RUN playwright install chromium

COPY monitor_single.py .
COPY jwt.txt .
COPY subkey.txt .

CMD ["python", "monitor_single.py"]