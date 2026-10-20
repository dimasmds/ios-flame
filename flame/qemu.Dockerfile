FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 qemu-system-arm && rm -rf /var/lib/apt/lists/*
WORKDIR /work
USER 1000:1000
