FROM ubuntu:oracular-20240811.1

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3-numpy=1:1.26.4+ds-11build1 \
    python3-scipy=1.13.1-3 \
    python3-matplotlib=3.8.3-3 \
    python3-pandas=2.2.2+dfsg-4 \
    python3-opencv=4.6.0+dfsg-14 \
    python3-psycopg2=2.9.9-1build1 \
    python3-pip

RUN pip3 install poetry==1.8.3 --break-system-packages
RUN poetry config virtualenvs.options.system-site-packages true
COPY ./pyproject.toml /app
COPY ./poetry.lock /app
RUN poetry install --without dev
