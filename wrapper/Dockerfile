# lmetl HTTP wrapper — POST /extract (docx -> structured JSON).
# Build from the lmetl repo root:  docker build -f wrapper/Dockerfile -t lmetl-extractor .
# Full python image (buildpack-deps) ships git, which uv needs to fetch lmetl's
# pwetl git dependency. (slim lacks git.)
FROM python:3.12

WORKDIR /app
RUN pip install --no-cache-dir uv

# Project + lockfile first for layer caching, then the rest of the source.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY configs ./configs
# Install lmetl + its locked deps, then add the wrapper's web deps to the same venv.
# (Kept out of pyproject/uv.lock to avoid touching lmetl's core dependency set.)
RUN uv sync --frozen --no-dev \
 && uv pip install fastapi "uvicorn[standard]"

COPY wrapper ./wrapper

ENV LMETL_CONFIG=configs/base.yaml
# If runtime genre switching needs schemas materialised, pre-sync here, e.g.:
# RUN uv run python -m lmetl.tools.sync_schemas configs/base.yaml

EXPOSE 9400
CMD ["uv", "run", "uvicorn", "wrapper.app:app", \
     "--host", "0.0.0.0", "--port", "9400", "--timeout-keep-alive", "75"]
