#!/bin/bash
set -ex

REPO=$1
BRANCH=$2
DIRECTORY=$3
REPOS_FILE=$4

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

UPGRADE_PATH="/opt/ou/OpenUpgrade/openupgrade_scripts/scripts"
if [[ -d "upgrade_scripts" ]] ; then
    UPGRADE_PATH=$UPGRADE_PATH,/opt/ou/step/$DIRECTORY/upgrade_scripts
fi
echo $UPGRADE_PATH

# Create odoo.cfg
envsubst < /opt/ou/odoo.cfg.tpl > /opt/ou/odoo.cfg

# Run preparation script
if [[ -f pre.sh ]] ; then
    . pre.sh
fi

# Run main script or use default behaviour (migrate)
if [[ ! -f run.sh ]] ; then
    odoo \
        --config "/opt/ou/odoo.cfg" \
        --upgrade-path="$UPGRADE_PATH" \
        --load=web,base,openupgrade_framework \
        --update all \
        --stop-after-init \
        --database "$PGDATABASE"
else
    . run.sh
fi

# Run post script
if [[ -f post.sh ]] ; then
    . post.sh
else
    mkdir /opt/ou/out
    click-odoo-backupdb -c "/opt/ou/odoo.cfg" --format "zip" --filestore  "$PGDATABASE" "/opt/ou/out/result.zip"
fi
