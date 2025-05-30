#!/bin/bash

kubectl create namespace monitoring
curl -fsS https://raw.githubusercontent.com/grafana/loki/master/tools/promtail.sh \
    | sh -s 1229788 ${PROMTAIL_TOKEN} ${LOKI_URL} monitoring \
    | kubectl apply --namespace=monitoring -f  -