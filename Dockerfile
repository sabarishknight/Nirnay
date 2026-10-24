FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY web web
COPY world world
COPY sql sql
COPY data/out data/out
ENV PORT=8080 PYTHONUNBUFFERED=1
CMD ["python", "app/main.py"]
