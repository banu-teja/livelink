FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

RUN useradd --create-home --shell /bin/bash relaykit

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY examples/ examples/

RUN uv pip install --system ".[gemini,serve]"

USER relaykit

EXPOSE 8000

ENV PORT=8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "examples/docker_voice/main.py"]
