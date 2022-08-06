FROM ubuntu:22.04

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
    libdc1394-dev

RUN apt-get update && apt-get install -y \
    python3-numpy=1:1.21.5-1build2 \
    python3-scipy=1.8.0-1exp2ubuntu1 \
    python3-matplotlib=3.5.1-2build1 \
    python3-pandas=1.3.5+dfsg-3 \
    python3-opencv=4.5.4+dfsg-9ubuntu4 \
    python3-psycopg2=2.9.2-1build2

# Requirements
COPY ./requirements.txt /app
RUN pip3 install -r requirements.txt
