#!/usr/bin/env bash
# Software will not work without the required Access and Secret Key
# Access key and Secret key can be found at: /nfs/users/nfs_m/mercury/.s3cfg
# These should be entered into the appropriate variables
export S3_AWS_ACCESS_KEY=""
export S3_AWS_SECRET_KEY=""
export S3_SANGER_URL="https://cog.sanger.ac.uk"
export S3_GROUP_NAME="{{ group_name }}"

cd /home/ubuntu
git clone https://github.com/wtsi-hgi/sapling.git
ansible-playbook /home/ubuntu/sapling/local.yml
