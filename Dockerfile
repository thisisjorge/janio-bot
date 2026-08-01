FROM denoland/deno:bin-2.9.4 AS deno

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=deno /deno /usr/local/bin/deno
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 janio \
    && mkdir -p /app/data \
    && chown -R janio:janio /app

USER janio

CMD ["python", "-m", "janio_bot"]
