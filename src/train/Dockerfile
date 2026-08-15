# Python base image has to match the python version
# that you use locally.
FROM python:3.8-slim

RUN apt-get update && apt-get install -y libgomp1
RUN pip3 install --upgrade pip
COPY src/train/requirements.txt ./requirements.txt
RUN pip3 install -r requirements.txt

RUN mkdir -p /app/src/ && \
    mkdir -p /app/model && \
    mkdir -p /app/data && \
    mkdir -p /app/.cache

COPY src/train/train.py /app/src/
COPY data/ /app/data/
ENV DATA_SOURCE=/app/data
ENV OUTPUT_PATH=/app/model

RUN chgrp -R 65534 /app && \
    chmod -R 770 /app && \
    # WORKAROUND: Allow sentence-transformers package to cache model.
    # Not to be used for production.
    chmod 777 /app/.cache