# The API image. The `forge` package is installed from the release the
# lockfile pins, so this repository is the whole build context.
#
# While `[tool.uv.sources]` names the sibling checkout `../forge` instead, the
# build is given that checkout as the named context `forge`, which takes the
# place of the empty stage below and lands at /opt/unicon/forge, the path the
# lockfile's `../forge` means from /opt/unicon/backend:
#
#     docker build --build-context forge=../forge .
#
# Built from a release pin, nothing replaces the stage and the directory stays
# empty.
FROM scratch AS forge


# npm resolves a task's npm packages and Coursier its Maven packages, while
# the task's packages are prepared; each is pinned by its SHA-256.
FROM python:3.14-slim-trixie AS tools-amd64
ADD --checksum=sha256:d28a96af6c38596f6d9d97c0ee531c13d238d757742387d1928de822d959e997 \
    https://nodejs.org/dist/v26.13.0/node-v26.13.0-linux-x64.tar.xz /tmp/node.tar.xz
ADD --checksum=sha256:348e37bc2a8c706640e6b032c4551a0e055a7f1537485b4a91540e9d3598ec6d \
    https://github.com/coursier/coursier/releases/download/v2.1.26/cs-x86_64-pc-linux.gz /tmp/cs.gz

FROM python:3.14-slim-trixie AS tools-arm64
ADD --checksum=sha256:406fe3fbde1c054adff8b297c16fdb5af6659db327c1ac8acd46b56ef1af9a92 \
    https://nodejs.org/dist/v26.13.0/node-v26.13.0-linux-arm64.tar.xz /tmp/node.tar.xz
ADD --checksum=sha256:6c358ac223332c8981eb86417d3faf9338a5ef6c95d1879a58162b24c510025c \
    https://github.com/coursier/coursier/releases/download/v2.1.26/cs-aarch64-pc-linux.gz /tmp/cs.gz

FROM tools-${TARGETARCH} AS tools
RUN python -c "import gzip, shutil, tarfile; \
tarfile.open('/tmp/node.tar.xz').extractall('/opt', filter='data'); \
shutil.copyfileobj(gzip.open('/tmp/cs.gz'), open('/opt/cs', 'wb'))" \
    && mv /opt/node-v26.13.0-linux-* /opt/node \
    && rm -rf /opt/node/include /opt/node/share /opt/node/*.md \
    && chmod 0755 /opt/cs


FROM python:3.14-slim-trixie AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /opt/unicon/backend
COPY --from=forge / /opt/unicon/forge/
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN uv sync --frozen --no-dev --no-install-project
COPY unicon ./unicon
RUN uv sync --frozen --no-dev


FROM python:3.14-slim-trixie

# Node needs libatomic on arm64.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 unicon \
    && mkdir -p /var/cache/unicon/resolve \
    && chown unicon:unicon /var/cache/unicon/resolve
COPY --from=build --chown=unicon:unicon /opt/unicon /opt/unicon
COPY --from=tools /opt/node /opt/node
COPY --from=tools /opt/cs /usr/local/bin/cs
WORKDIR /opt/unicon/backend
ENV PATH="/opt/unicon/backend/.venv/bin:/opt/node/bin:$PATH" PYTHONUNBUFFERED=1
ENV UNICON_RESOLVE_CACHE=/var/cache/unicon/resolve
USER unicon
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()"

ENTRYPOINT ["unicon"]
CMD ["api"]
