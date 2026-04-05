#!/bin/sh
set -e

if [ -z "$P_VALUE" ]; then
    echo "Error: P_VALUE environment variable not set"
    exit 1
fi

echo "Raw P_VALUE=$P_VALUE"

case "$P_VALUE" in
  0)
    USER_SERVICE_V1_WEIGHT=0
    ;;
  1)
    USER_SERVICE_V1_WEIGHT=100
    ;;
  0.5)
    USER_SERVICE_V1_WEIGHT=50
    ;;
  *)
    echo "Error: P_VALUE must be 0, 0.5, or 1"
    exit 1
    ;;
esac

USER_SERVICE_V2_WEIGHT=$((100 - USER_SERVICE_V1_WEIGHT))

export USER_SERVICE_V1_WEIGHT
export USER_SERVICE_V2_WEIGHT

echo "USER_SERVICE_V1_WEIGHT=$USER_SERVICE_V1_WEIGHT"
echo "USER_SERVICE_V2_WEIGHT=$USER_SERVICE_V2_WEIGHT"

envsubst < /etc/kong/kong.yml.template > /etc/kong/kong.yml

kong prepare -p /usr/local/kong

exec kong start --nginx-conf /usr/local/kong/nginx.conf