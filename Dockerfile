FROM ubuntu:20.10

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    checkinstall \
    cmake \
    pkg-config \
    yasm \
    python3-pip \
    python3-dev \
    libffi-dev \
    libssl-dev \
    libgtk-3-dev \
    libavcodec-dev \
    libavformat-dev \
    libswscale-dev \
    libv4l-dev \
    libxvidcore-dev \
    libx264-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    gfortran openexr \
    libatlas-base-dev \
    libtbb2 \
    libtbb-dev \
    libdc1394-22-dev

RUN apt-get install -y \
    python3-pigpio=1.68-4 \
    python3-numpy=1:1.18.4-1ubuntu1 \
    python3-scipy=1.4.1-2 \
    python3-matplotlib=3.2.2-1 \
    python3-pandas=0.25.3+dfsg2-3 \
    python3-opencv=4.2.0+dfsg-6build3

# Requirements
RUN pip3 install poetry==1.0.5
COPY ./pyproject.toml /app
COPY ./poetry.lock /app
RUN poetry config virtualenvs.create false && \
    poetry install
