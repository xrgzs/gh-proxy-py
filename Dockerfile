FROM python:3.13-slim

LABEL maintainer="MadDogOwner <xiaoran@xrgzs.top>"

EXPOSE 8000

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements
RUN pip install --no-cache-dir flask requests gunicorn

COPY ./app /app
WORKDIR /app

# Make /app/* available to be imported by Python globally to better support several use cases like Alembic migrations.
ENV PYTHONPATH=/app

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

ENV LISTEN_ADDR=0.0.0.0:8000

CMD ["sh", "-c", "gunicorn --bind ${LISTEN_ADDR} main:app"]
