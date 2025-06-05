#!/usr/bin/env bash
kubectl create namespace argocd
kubectl apply -k . -n argocd
