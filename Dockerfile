FROM python:3.13-slim

LABEL maintainer="MadDogOwner <xiaoran@xrgzs.top>"

EXPOSE 8000

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Make /app/* available to be imported by Python globally to better support several use cases like Alembic migrations.
ENV PYTHONPATH=/app

# Creates a non-root user with an explicit UID
RUN adduser -u 5678 --disabled-password --gecos "" appuser
USER appuser

# Install pip requirements
COPY --chown=appuser ./requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the content of the app folder to /app inside the container
COPY --chown=appuser ./app /app
WORKDIR /app

# Start the server
ENV LISTEN_ADDR=0.0.0.0:8000

ENV WEB_CONCURRENCY=4

CMD ["sh", "-c", "gunicorn --bind ${LISTEN_ADDR} --worker-class gevent --timeout 300 main:app"]
