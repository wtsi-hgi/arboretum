#!/usr/bin/env bash

set -e
set -u
set -x

sudo bash "wait-for-apt-lock.sh"
sudo apt-get update
sleep 5
sudo bash "wait-for-apt-lock.sh"
sudo apt-get install -y python-pip
exit
