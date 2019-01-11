#!/bin/bash
supervisorctl stop all
supervisorctl remove cnap_celery_beat
supervisorctl remove cnap_celery_worker
supervisorctl remove redis
echo "" >/var/log/cnap/celery_worker.log
echo "" >/var/log/cnap/celery_beat.log
echo "" >/var/log/cnap/redis.log
