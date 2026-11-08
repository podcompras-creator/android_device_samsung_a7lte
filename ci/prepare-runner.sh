#!/usr/bin/env bash
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]] || { echo 'Cleanup is restricted to an ephemeral GitHub-hosted runner'; exit 2; }
df -h /
# Explicitly authorized cleanup of the disposable Actions image only.
sudo rm -rf /usr/share/dotnet /opt/ghc /usr/local/.ghcup /usr/local/lib/android /usr/local/share/boost /opt/hostedtoolcache/CodeQL
mapfile -t REMOVE < <(dpkg-query -W -f='${binary:Package}\n' | awk '/^(dotnet-|aspnetcore-|ghc|haskell-|azure-cli)/')
if ((${#REMOVE[@]})); then sudo apt-get purge -y "${REMOVE[@]}"; fi
sudo docker image prune --all --force || true
sudo apt-get clean
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  bc bison build-essential ccache curl flex g++-multilib gcc-multilib git gnupg \
  gperf imagemagick lib32ncurses5-dev lib32readline-dev lib32z1-dev liblz4-tool \
  libncurses5 libncurses5-dev libtinfo5 libsdl1.2-dev libssl-dev libxml2 libxml2-utils \
  lzop pngcrush rsync schedtool squashfs-tools xsltproc zip unzip zlib1g-dev \
  python2 python3 openjdk-8-jdk libelf-dev m4 ca-certificates
sudo apt-get clean
ccache -M 2G
df -h /
