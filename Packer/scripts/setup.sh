#!/usr/bin/env bash

set -eux

sudo bash "wait-for-apt-lock.sh"
sudo apt-get update
sudo bash "wait-for-apt-lock.sh"
sudo apt-get install -y python-pip
exit
