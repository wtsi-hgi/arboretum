# Packer
The code within this file is used to build the image 'hgi-arboretum-image' which
is used by arboretum as the base OpenStack image for the creation of instances.

## Extra requirements
In order for the image file to work, packer is required to be installed on the instance.
An OpenRC V3 will also need to be installed and placed in this directory of child folders (/scipts/).
For this to work with packer, OS_PROJECT_NAME and OS_PROJECT_ID need to be swapped for OS_TENANT_NAME
and OS_TENANT_ID respectively. OS_USER_DOMAIN_NAME will need to be changed to OS_DOMAIN_NAME. Remove
the unset of OS_TENANT_ID and OS_TENANT_NAME.

## Usage
Run the command:

        . ./{PATH-OF-OpenRC-FIEL}

This will request your OpenStack Password.
By running the command:

        packer build image.json

An OpenStack image will be built. Depending on apt/dpkg resource locking, the build
can take in excess of 15 minutes. Once completed, the image should be loaded onto
OpenStack and should be ready to use.
