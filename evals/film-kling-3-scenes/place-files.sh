#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/files/." .
python mock_kling/server.py 8710 mock_kling/out > mock_kling/server.err 2>&1 &
