#!/bin/bash
set -eu
exec 3<>/dev/tcp/127.0.0.1/5000
printf 'GET /nearest/v1/driving/92.85,56.01?number=1 HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n' >&3
read -r status <&3
[[ "$status" == *' 200 OK'* ]]
