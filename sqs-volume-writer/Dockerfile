FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

ENV OUTPUT_DIR=/data
VOLUME /data

ENTRYPOINT ["python", "-u", "main.py"]
