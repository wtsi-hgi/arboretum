#!/usr/bin/env bash
export S3_AWS_ACCESS_KEY=""
export S3_AWS_SECRET_KEY=""
export S3_SANGER_URL="https://cog.sanger.ac.uk"
export S3_GROUP_NAME="{{ group_name }}"

cd /home/ubuntu
git clone https://github.com/wtsi-hgi/sapling.git
ansible-playbook /home/ubuntu/sapling/local.yml

