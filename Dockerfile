FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# Optional: expose a port (Render ignores it but good practice)
EXPOSE 8000

CMD ["python", "bot.py"]
