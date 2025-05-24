FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

EXPOSE 8002

ENV HTTP_PORT=8002
ENV TARGET_TCP_PORT=8003
ENV TARGET_IP=localhost

CMD ["python", "main.py"] 