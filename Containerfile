# Isolated legacy userspace for Pie; source inputs are pinned separately.
FROM ubuntu:22.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    android-sdk-libsparse-utils bc bison build-essential checkpolicy e2fsprogs ca-certificates ccache curl flex g++-multilib gcc-multilib \
    git gnupg gperf imagemagick lib32ncurses5-dev lib32z1-dev libelf-dev liblz4-tool \
    libncurses5 libncurses5-dev libselinux1-dev libsepol-dev libsdl1.2-dev libssl-dev libtinfo5 libxml2 libxml2-utils \
    lz4 lzop m4 openjdk-8-jdk pngcrush python2 python3 rsync schedtool squashfs-tools unzip \
    xsltproc xz-utils zip zlib1g-dev && rm -rf /var/lib/apt/lists/*
# Use: docker run --rm --user "$(id -u):$(id -g)" -v /large:/work -w /work IMAGE ...
RUN ln -s /usr/bin/python2 /usr/local/bin/python
ARG BUILDER_UID=1000
ARG BUILDER_GID=1000
RUN groupadd --gid ${BUILDER_GID} builder && useradd --uid ${BUILDER_UID} --gid ${BUILDER_GID} --create-home builder
USER builder
WORKDIR /work
