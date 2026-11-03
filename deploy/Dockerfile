FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY configs ./configs
RUN pip install --no-cache-dir .
# catalog_file() walks parents of the installed module, not WORKDIR.
COPY configs /usr/local/configs
# The PyPI wheel does not land in DuckDB's extension directory.
# INSTALL here so a later LOAD does not download. INSTALL at runtime hangs offline.
RUN python -c "import duckdb; c=duckdb.connect(); c.execute('INSTALL httpfs')"

EXPOSE 8080
CMD ["fas-api"]
