FROM debian:stretch

RUN apt-get update \
    && apt-get install -y \
    build-essential \
    python3-dev \
    python3-pip \
    python3-cffi \
    python3-cryptography \
    wget \
    curl

ARG dropbox_dir=/opt/dropbox_transfer
RUN mkdir -p ${dropbox_dir}
ADD requirements.txt ${dropbox_dir}/

ADD container_startup.py ${dropbox_dir}/
RUN pip3 install --no-cache -r ${dropbox_dir}/requirements.txt

ENTRYPOINT ["/opt/dropbox_transfer/container_startup.py"]
