FROM python:3.13-slim

LABEL maintainer="MadDogOwner <xiaoran@xrgzs.top>"

RUN pip install --no-cache-dir flask requests gunicorn

COPY ./app /app
WORKDIR /app

# Make /app/* available to be imported by Python globally to better support several use cases like Alembic migrations.
ENV PYTHONPATH=/app

ENV LISTEN_ADDR=0.0.0.0:8000

CMD ["sh", "-c", "gunicorn --bind ${LISTEN_ADDR} main:app"]

EXPOSE 8000
