FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN python -m spacy download en_core_web_sm

COPY . .

# Copy frontend HTML into Flask static folder
RUN mkdir -p static && cp -r frontend/* static/

EXPOSE 8080
CMD ["python", "backend/app.py"]
