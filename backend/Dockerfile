FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false
ENV POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir poetry==2.0.1

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main

COPY app ./app
COPY run_seed.py ./run_seed.py

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
