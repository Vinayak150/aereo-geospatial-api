FROM python:3.12.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PROJ_NETWORK=OFF \
    AEREO_DATABASE_URL=sqlite:////data/aereo.db
WORKDIR /srv
COPY requirements.lock .
RUN pip install --no-cache-dir --upgrade pip==26.2.1 \
    && pip install --no-cache-dir --only-binary=:all: -r requirements.lock \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir /data && chown app:app /data
COPY app ./app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "8"]
