FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/ ./config/
RUN pip install --no-cache-dir -e .

# corre como utilizador nao-root
RUN useradd --create-home --uid 10001 bot && mkdir -p /app/data && chown -R bot /app
USER bot

CMD ["python", "-m", "plumbybit"]
