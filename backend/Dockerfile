FROM python:3.11-slim AS build-deps

WORKDIR /build

# Compilers and headers are only needed when pip builds a wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

WORKDIR /app

# Weka requires a JVM. Keep only runtime libraries in the production image.
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libgomp1 libpq5 openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build-deps /install/ /usr/local/
COPY . .

RUN adduser --disabled-password --gecos '' appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "python scripts/render_check_env.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
