FROM python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN python -m spacy download en_core_web_sm

# Copy everything to the container
COPY . .

# Create the static directory structure that Flask expects
RUN mkdir -p backend/frontend
RUN if [ -d "frontend" ]; then cp -r frontend/* backend/frontend/ || echo "No frontend files to copy"; fi

# Set the working directory to where app.py is located
WORKDIR /app/backend

EXPOSE 8080

# Run the app from the backend directory
CMD ["python", "app.py"]