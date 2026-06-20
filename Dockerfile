FROM ubuntu:resolute-20260108

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    make \
    build-essential \
    python3-numpy=1:2.3.5+* \
    python3-scipy=1.16.3-* \
    python3-matplotlib=3.10.7+* \
    python3-pandas=2.3.3+* \
    python3-opencv=4.10.0+* \
    python3-psycopg2=2.9.11-* \
    python3-pip

RUN pip3 install poetry==2.3.2 --break-system-packages
RUN poetry config virtualenvs.options.system-site-packages true
COPY ./pyproject.toml /app
COPY ./poetry.lock /app
RUN poetry install --without dev
