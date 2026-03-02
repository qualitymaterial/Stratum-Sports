#!/bin/sh
IMAGE_TAG=abc
ref='ghcr.io/x:y'
case "$ref" in
  *:latest)
    echo latest
    ;;
  *:"$IMAGE_TAG")
    echo ok
    ;;
  *)
    echo bad
    ;;
esac
