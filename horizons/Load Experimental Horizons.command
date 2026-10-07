#!/bin/zsh
cd "${0:A:h}" || exit 1
/usr/bin/python3 tools/prepare_client.py load
read -r "?Press Return to close."
