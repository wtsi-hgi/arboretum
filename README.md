THIS PROGRAM IS NOT YET FULLY FUNCTIONAL
========================================

# Arboretum
Arboretum helps automate the creation, destruction, and monitoring of [Branchserve](https://github.com/wtsi-hgi/branchserve) instances. A web frontend called [Warden](https://github.com/wtsi-hgi/warden) is available.

### Dependencies
Python libraries:
 - `jinja2`
 - `openstacksdk`
 - `service`
 - `hug`
 - `gunicorn`

`s3cmd` must be installed.

### Quick start guide

For Arboretum to work, S3 (`~/.s3cfg`) and OpenStack (`~/.config/openstack/clouds.yaml`) config files have to be present on the machine. Enter the S3 access and secret keys into `user.sh`, the script will be passed to created machines as userdata.

Arboretum has the following commands:
 - `start` - start the Arboretum daemon
 - `stop` - stop the Arboretum daemon
 - `create/destroy [group]` - launch/destroy a Branchserve instance for Unix group [group]'s data
 - `update` - Fetch mpistat data from S3 and create a catalogue of available groups
 - `group` - Print a JSON dump of available groups and their statuses

 `api.py` is an API for some Arboretum functionality. Run it using `gunicorn`: `gunicorn -b 0.0.0.0:8000 api:__hug_wsgi__`.
  - `/groups` - JSON list of all available groups and their estimated system requirements
  - `/create?group=[group]` - Tell Arboretum to launch `[group]`'s Branchserve instance
  - `/destroy?group=[group]` - Tell Arboretum to destroy `[group]`'s Branchserve instance
