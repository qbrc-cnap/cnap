FROM ubuntu:xenial

RUN apt-get update \
    && apt-get install -y \
    build-essential \
    libssl-dev \
    python3-dev \
    python3-pip \
    python3-cffi \
    python3-cryptography \
    wget \
    curl \
    lsb-release

RUN export GCSFUSE_REPO=gcsfuse-`lsb_release -c -s` \
    && echo "deb http://packages.cloud.google.com/apt $GCSFUSE_REPO main" | tee /etc/apt/sources.list.d/gcsfuse.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add - \
    && apt-get update \
    && apt-get install -y gcsfuse

ARG dropbox_dir=/opt/dropbox_transfer
RUN mkdir -p ${dropbox_dir}
ADD requirements.txt ${dropbox_dir}/

ADD container_startup.py ${dropbox_dir}/
RUN pip3 install --no-cache -r ${dropbox_dir}/requirements.txt

ENTRYPOINT ["/opt/dropbox_transfer/container_startup.py"]
