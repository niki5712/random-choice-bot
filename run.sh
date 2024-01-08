#!/bin/bash
ROOT_DIR=$(dirname "$0")

source "$ROOT_DIR/venv/bin/activate"

pushd "$ROOT_DIR/src" > /dev/null
    eval $(cat "../.env"; echo 'python main.py')
popd > /dev/null

deactivate
