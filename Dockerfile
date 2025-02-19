FROM ghcr.io/astral-sh/uv:0.6.1-python3.12-alpine

ADD . /unicon-backend
WORKDIR /unicon-backend

# Install dependencies
RUN uv sync --frozen --no-dev

ENTRYPOINT ["uv", "run", "fastapi", "run", "unicon_backend/app.py"]