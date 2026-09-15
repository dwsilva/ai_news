FROM python:3.12-slim

# weasyprint precisa de pango/cairo para gerar o PDF e graphviz e usado no diagrama de arquitetura.
RUN apt-get update && apt-get install -y --no-install-recommends \
        graphviz \
        libcairo2 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[dev]"

COPY tests ./tests
COPY docs ./docs

EXPOSE 8000
CMD ["uvicorn", "srag.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
