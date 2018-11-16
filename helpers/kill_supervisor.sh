#!/bin/bash
supervisorctl stop all
supervisorctl remove transfer_celery_beat
supervisorctl remove transfer_celery_worker
supervisorctl remove redis
echo "" >/var/log/cnap_v2/celery_worker.log
echo "" >/var/log/cnap_v2/celery_beat.log
echo "" >/var/log/cnap_v2/redis.log
