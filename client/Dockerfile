FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tcp_to_http.py .

EXPOSE 8001
EXPOSE 9001

ENV TCP_PORT=8001
ENV TARGET_HTTP_PORT=8002
ENV RESPONSE_HTTP_PORT=9001
ENV TARGET_IP=http_to_tcp_service

CMD ["python", "tcp_to_http.py"] 