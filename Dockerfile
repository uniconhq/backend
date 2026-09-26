# The API image. The `forge` package is installed from the release the
# lockfile pins, so this repository is the whole build context.
FROM python:3.14-slim-trixie AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /opt/unicon/backend
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY unicon ./unicon
RUN uv sync --frozen --no-dev


FROM python:3.14-slim-trixie

RUN useradd --create-home --uid 10001 unicon
COPY --from=build --chown=unicon:unicon /opt/unicon /opt/unicon
WORKDIR /opt/unicon/backend
ENV PATH="/opt/unicon/backend/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER unicon
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()"

ENTRYPOINT ["unicon"]
CMD ["api"]
