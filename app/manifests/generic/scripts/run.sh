#!/bin/bash
set -ex

if [[ ! -z "$GIT_PAT" ]]; then
    REPO=$(echo "$REPO" | sed "s,https://,https://${GIT_PAT}@,")
fi

git clone --depth 1 -b "$BRANCH" "$REPO" step
cd "step/$DIRECTORY"

# Aggregate repos and update addons_path
if [[ -f "$REPOS_FILE" ]] ; then
    gitaggregate -c "$REPOS_FILE" --expand-env
    ADDONS_PATH=$ADDONS_PATH,$(find $(pwd)/* -name .git -exec dirname {} \; | uniq | tr '\n' ',' | sed 's/,$//')
fi

echo $ADDONS_PATH

# Install requirements
if [[ -f "requirements.txt" ]] ; then
    pip install --no-cache-dir -r requirements.txt
fi

# Create odoo.cfg
envsubst < /opt/ou/odoo.cfg.tpl > /opt/ou/odoo.cfg

odoo -c "/opt/ou/odoo.cfg" --db-filter "^$PGDATABASE$" --no-database-list
