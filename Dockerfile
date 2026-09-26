FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 sylvex && mkdir -p webapp/generated backend/preset_catalog && chown -R sylvex:sylvex /app
USER sylvex
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
