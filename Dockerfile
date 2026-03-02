FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
RUN mkdir -p templates
COPY templates/dashboard.html templates/dashboard.html

EXPOSE 5000

# Timeout raised to 120s to handle slow ConnectWise API responses
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--graceful-timeout", "30", "app:app"]
