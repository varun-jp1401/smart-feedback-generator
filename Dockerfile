FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Try to download spaCy model, but don't fail if it doesn't work
RUN python -m spacy download en_core_web_sm || echo "spaCy model download failed, continuing..."

# Copy the application code
COPY . .

# Create necessary directories and ensure data folder is copied
RUN mkdir -p data
COPY data/ ./data/

# List files to verify structure (for debugging)
RUN echo "Files in working directory:" && ls -la
RUN echo "Files in data directory:" && ls -la data/ || echo "No data directory found"

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Expose the port that Railway will assign
EXPOSE $PORT

# Use Flask's built-in server with better error handling
CMD ["python", "app.py"]