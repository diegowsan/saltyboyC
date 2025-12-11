FROM python:3.11-slim

# Keep Python from buffering stdout so logs appear instantly
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (Required for Postgres)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --upgrade pip && pip install poetry

# Copy dependencies
COPY pyproject.toml poetry.lock* ./

# Install Python packages (No virtualenv needed in Docker)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root --without=dev

# Copy the app
COPY src ./src
COPY main.py .

# Run directly
CMD ["python", "main.py"]