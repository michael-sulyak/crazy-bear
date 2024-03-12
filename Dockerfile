FROM ubuntu:mantic-20240216

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update

RUN apt-get install -y \
    python3-numpy=1:1.24.2-1 \
    python3-scipy=1.10.1-2 \
    python3-matplotlib=3.6.3-1ubuntu2 \
    python3-pandas=1.5.3+dfsg-6 \
    python3-opencv=4.6.0+dfsg-13build1 \
    python3-psycopg2=2.9.6-2

RUN apt-get install -y python3-pip

# Requirements
RUN pip3 install poetry==1.7.1  --break-system-packages
RUN poetry config virtualenvs.options.system-site-packages true
COPY ./pyproject.toml /app
COPY ./poetry.lock /app
RUN poetry install --without dev

RUN export PYTHONPATH="/usr/local/lib/python3.11/dist-packages:/usr/lib/python3/dist-packages:/usr/lib/python3.11/dist-packages"
