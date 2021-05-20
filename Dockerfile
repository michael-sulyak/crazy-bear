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

RUN apt-get update && apt-get install -y \
    python3-numpy=1:1.18.4-1ubuntu1 \
    python3-scipy=1.5.2-2 \
    python3-matplotlib=3.3.0-3 \
    python3-pandas=1.0.5+dfsg-3 \
    python3-opencv=4.2.0+dfsg-6build6

# Requirements
COPY ./requirements.txt  /app
RUN pip3 install -r requirements.txt
