FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    python -m spacy download en_core_web_sm

# Copy the entire project
COPY . .

# Create necessary directories
RUN mkdir -p backend/frontend backend/data

# Copy frontend files if they exist
RUN if [ -d "frontend" ]; then cp -r frontend/* backend/frontend/ || true; fi

# Copy data files if they exist
RUN if [ -d "data" ]; then cp -r data/* backend/data/ || true; fi

# Set working directory to backend
WORKDIR /app/backend

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application
CMD ["python", "app.py"]