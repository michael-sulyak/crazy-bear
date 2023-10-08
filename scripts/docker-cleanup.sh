#!/bin/bash

# Clear up unused image
docker rmi $(docker images -q)

# Clean up unused docker volumes
docker volume rm $(docker volume ls -qf dangling=true)

# Clear logs
truncate -s 0 /var/lib/docker/containers/**/*-json.log
