#!/bin/bash
set -e

# This script is run upon entering the container.  It fills in various 
# templates and queries the user about configuration options, parameters.

# e.g. production or dev
export DEPLOYMENT=$1

cd $APP_ROOT

# Fill out the general config and copy the templates
# that do not need configuration
printf "Enter some configuration parameters\n"
printf "======================================\n\n\n"
python3 helpers/fill_config_templates.py
cd config
cp downloaders.template.cfg downloaders.cfg 
cp uploaders.template.cfg uploaders.cfg 
cp live_tests.template.cfg live_tests.cfg 

cd $APP_ROOT

# create log dir and touch log files:
export LOGDIR="/var/log/cnap"
export CELERY=$(which celery)
mkdir -p $LOGDIR
touch $LOGDIR/redis.log
touch $LOGDIR/celery_beat.log
touch $LOGDIR/celery_worker.log
touch $LOGDIR/gunicorn.log

# Fill-out and copy files for supervisor-managed processes:
python3 helpers/fill_supervisor_templates.py \
    /etc/supervisor/conf.d \
    supervisor_conf_files/celery_worker.conf \
    supervisor_conf_files/celery_beat.conf \
    supervisor_conf_files/redis.conf \
    supervisor_conf_files/gunicorn.conf

# start supervisor:
supervisord --configuration /etc/supervisor/supervisord.conf
supervisorctl reread && supervisorctl update

# setup database:
printf "Setup the database"
python3 manage.py makemigrations
python3 manage.py migrate

# populate the zones into the db:
python3 helpers/populate_zones.py

# add some content for non-trivial views (using the test account)
python3 helpers/populate_and_prep_db.py

# Run collectstatic so the static assets will be in a single location:
python3 manage.py collectstatic
python3 helpers/move_static_files.py

# Need to add parameters (e.g. api key) into javascript file:
# Note that this needs to happen after the template configs above,
# as this script pulls details that were filled into the config files.
# Also needs to have run collectstatic prior
python3 helpers/fill_javascript.py

printf "\n\n\nCreate a super user:"
python3 manage.py createsuperuser