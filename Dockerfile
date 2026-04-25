FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./pyproject.toml
COPY agent ./agent
COPY products.yaml ./products.yaml
COPY docs ./docs
COPY start.sh ./start.sh

RUN python -m pip install --upgrade pip && pip install -e .

EXPOSE 8000

CMD ["pulse", "serve", "--host", "0.0.0.0", "--port", "8000"]
