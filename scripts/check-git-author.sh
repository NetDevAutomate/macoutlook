#!/usr/bin/env bash
# Pre-commit hook: ensure git author email is correct for this repo
EXPECTED="andy.taylor@mail.com"
ACTUAL=$(git config user.email)

if [ "$ACTUAL" != "$EXPECTED" ]; then
    echo "ERROR: git author email is '$ACTUAL' — expected '$EXPECTED'"
    echo "Fix with: git config user.email $EXPECTED"
    exit 1
fi
