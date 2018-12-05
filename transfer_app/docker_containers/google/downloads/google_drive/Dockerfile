FROM ubuntu:xenial

RUN apt-get update \
    && apt-get install -y \
    build-essential \
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

ARG drive_dir=/opt/drive_transfer
RUN mkdir -p ${drive_dir}
ADD requirements.txt ${drive_dir}/

ADD container_startup.py ${drive_dir}/
RUN pip3 install --no-cache -r ${drive_dir}/requirements.txt

ENTRYPOINT ["/opt/drive_transfer/container_startup.py"]
