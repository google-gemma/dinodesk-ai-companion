#!/bin/bash
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

function check_online
{
    netcat -z -w 5 8.8.8.8 53 && echo 1 || echo 0
}

# Initial check to see if we are online
IS_ONLINE=$(check_online)
# How many times we should check if we're online - this prevents infinite looping
MAX_CHECKS=5
# Initial starting value for checks
CHECKS=0

# Loop while we're not online.
while [ $IS_ONLINE -eq 0 ]; do
    echo "..waiting for network.."
    sleep 10;
    IS_ONLINE=$(check_online)

    CHECKS=$[ $CHECKS + 1 ]
    if [ $CHECKS -gt $MAX_CHECKS ]; then
        break
    fi
done

if [ $IS_ONLINE -eq 0 ]; then
    echo "[NG] failed to connect the network."
    exit 1
fi

# Comment out below to create a SSH tunnel
#ssh -f -N -R 2400:localhost:22 -R 2401:localhost:5000 YOUR_SERVER_IP
#echo "[OK] tunnel created."

# Update the codes
cd /home/pi/dinodesk-ai-companion
git pull origin

# Launch DinoDesk App
export GATEWAY_URL="https://YOUR_DESKTOP_IP:8000/v1/chat/stream"
/home/pi/venv/bin/python /home/pi/dinodesk-ai-companion/rpi_client/main.py

