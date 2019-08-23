#!/bin/sh

rm -rf build dist
docker build -t zeus-voting/build .
docker run -ti -v "$(pwd):/src/" zeus-voting/build