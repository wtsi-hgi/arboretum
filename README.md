THIS PROGRAM IS NOT YET FULLY FUNCTIONAL
========================================

# Arboretum
Arboretum helps automate the creation, destruction, and monitoring of [Branchserve](https://github.com/wtsi-hgi/branchserve) instances. 

### Dependencies
Python libraries:
 - `jinja2`
 - `openstacksdk`
 - `service`
 - `hug`

`s3cmd` must be installed.

### Quick start guide

For Arboretum to work, S3 (`~/.s3cfg`) and OpenStack (`~/.config/openstack/clouds.yaml`) config files have to be present on the machine. Enter the S3 access and secret keys into `user.sh`, the script will be passed to created machines as userdata.

Arboretum has the following commands:
 - `start` - start the Arboretum daemon
 - `stop` - stop the Arboretum daemon
 - `create/destroy [group]` - launch/destroy a Branchserve instance for Unix group [group]'s data

 `warden.py` is an API for some Arboretum functionality. Run it using `hug`: `hug -p [port] -f warden.py`. If the port argument is omitted, 8000 is used.
  - /groups - JSON list of all available groups and their estimated system requirements
