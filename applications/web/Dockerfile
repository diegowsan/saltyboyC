# Use the lightweight "slim" version (Consistent with Bot)
FROM python:3.11-slim

# Prevent Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Install System Dependencies (CRITICAL for Postgres connection)
# We need gcc and libpq-dev so the dashboard can talk to the database
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Poetry
RUN pip install --upgrade pip \
    && pip install poetry

# 3. Copy Dependency Files
COPY pyproject.toml poetry.lock* ./

# 4. Configure & Install Dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root --without=dev

# 5. Copy Source Files (Including 'public' for static assets)
COPY public ./public
COPY src ./src
COPY main.py .

# 6. Expose the Dashboard Port
EXPOSE 5000

# 7. Run the Dashboard
# We skip 'entrypoint.sh' because we moved migration logic into the python code itself
CMD ["python", "main.py"]