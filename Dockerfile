FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 && rm -rf /var/lib/apt/lists/*
# The app user exists before the project is copied, so the files arrive
# already owned by it. A `chown -R /app` after `COPY . .` writes a second
# full copy of every project file into a new image layer.
RUN useradd --create-home --uid 10001 sylvex
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=sylvex:sylvex . .
RUN mkdir -p webapp/generated backend/preset_catalog && chown sylvex:sylvex /app webapp/generated backend/preset_catalog
# Root-owned, not writable by sylvex: what root runs at start cannot be
# changed by the service user. setpriv (util-linux) must exist; the build
# fails otherwise, so a broken image never replaces the running one.
COPY --chown=root:root docker-entrypoint.sh /usr/local/bin/sylvex-entrypoint
RUN chmod 755 /usr/local/bin/sylvex-entrypoint && command -v setpriv
USER sylvex
ENTRYPOINT ["/usr/local/bin/sylvex-entrypoint"]
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --no-proxy-headers"]
