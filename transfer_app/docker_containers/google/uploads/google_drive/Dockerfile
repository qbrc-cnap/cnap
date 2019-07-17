FROM debian:stretch

RUN apt-get update \
    && apt-get install -y \
    build-essential \
    python-dev \
    python3-dev \
    python3-pip \
    python3-cffi \
    python3-cryptography \
    wget \
    curl

RUN curl -sSL https://sdk.cloud.google.com > /tmp/gcl \
    && bash /tmp/gcl --install-dir=/root/gcloud --disable-prompts
ARG gcloud_bin=/root/gcloud/google-cloud-sdk/bin
ENV PATH "$PATH:"${gcloud_bin}

ARG drive_dir=/opt/drive_transfer
RUN mkdir -p ${drive_dir}
ADD requirements.txt ${drive_dir}/

ADD container_startup.py ${drive_dir}/
RUN pip3 install --no-cache -r ${drive_dir}/requirements.txt

ENTRYPOINT ["/opt/drive_transfer/container_startup.py"]
