#!/bin/bash

cd /home/elansol/Desktop/SCOUT_VISION/reciever

while true
do
    echo "Starting FireSmoke_receiver.py..."

    env -i \
    USER=elansol \
    HOME=/home/elansol \
    DISPLAY=:0 \
    XDG_RUNTIME_DIR=/run/user/1000 \
    CUDA_VISIBLE_DEVICES=0 \
    /usr/bin/python3 -u FireSmoke_receiver.py

    EXIT_CODE=$?

    echo "Process crashed/exited with code $EXIT_CODE"
    echo "Restarting in 3 seconds..."
    sleep 3
done
