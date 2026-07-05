FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy project configuration first (for layer caching)
COPY pyproject.toml ./

# Install dependencies
RUN uv pip install --system --no-cache -e .

# Copy application source code
COPY app/ ./app/

# Copy environment defaults (API key injected at runtime)
COPY .env.example .env.example

# Expose the application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the FastAPI server
CMD ["uvicorn", "app.fast_api_app:app", "--host", "0.0.0.0", "--port", "8000"]
