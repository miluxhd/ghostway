FROM python:3.9-slim

WORKDIR /app/tests

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bidirectional-tests.py .

ENV TCP_TO_HTTP_HOST=ghostway-client
ENV HTTP_TO_TCP_HOST=ghostway-server
ENV TCP_SERVER_HOST=ghostway-tests
ENV TCP_TO_HTTP_PORT=8001
ENV HTTP_TO_TCP_PORT=8002
ENV TCP_SERVER_PORT=8003
ENV RESPONSE_PORT=9001

COPY wait-for-it.sh /wait-for-it.sh
RUN chmod +x /wait-for-it.sh

CMD ["/bin/bash", "-c", "/wait-for-it.sh $TCP_TO_HTTP_HOST:$TCP_TO_HTTP_PORT -t 30 && python bidirectional-tests.py"]
