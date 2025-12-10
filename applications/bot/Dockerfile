# Use the lightweight "slim" version to save space
FROM python:3.11-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Install System Dependencies (CRITICAL for psycopg2/Postgres)
# We need gcc and libpq-dev to compile the database driver.
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Poetry
RUN pip install --upgrade pip \
    && pip install poetry

# 3. Copy Dependency Files (Cached Layer)
COPY pyproject.toml poetry.lock* ./

# 4. Configure & Install Dependencies
# We disable virtualenvs because Docker itself is the virtualenv
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root --without=dev

# 5. Copy Application Code
COPY src ./src
COPY main.py .

# 6. Run the Bot
# We use the python command directly, bypassing complex entrypoints
CMD ["python", "main.py"]