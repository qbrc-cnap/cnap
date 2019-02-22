#!/bin/bash 

# This script builds and pushes the docker containers that perform uploads
# You should already be logged into your docker account with `docker login`
# so that the docker push commands will work.  
#
# This script is mainly just a helper that I will run manually, so it is not
# particularly robust.


# the path to the root of the application (e.g. /www)
REPOSITORY_DIR=$1

cd $REPOSITORY_DIR/transfer_app/docker_containers/google/uploads/dropbox
docker build -t blawney/dropbox_upload_to_google .
docker push blawney/dropbox_upload_to_google

cd $REPOSITORY_DIR/transfer_app/docker_containers/google/uploads/google_drive
docker build -t blawney/drive_upload_to_google .
docker push blawney/drive_upload_to_google

cd $REPOSITORY_DIR/transfer_app/docker_containers/google/downloads/dropbox
docker build -t blawney/dropbox_in_google .
docker push blawney/dropbox_in_google

cd $REPOSITORY_DIR/transfer_app/docker_containers/google/downloads/google_drive
docker build -t blawney/drive_in_google .
docker push blawney/drive_in_google
