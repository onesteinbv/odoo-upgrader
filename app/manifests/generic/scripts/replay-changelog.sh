#!/bin/bash
mkdir /opt/ou/out

python odoo-upgrader/replay-changelog.py

# Create odoo.cfg
envsubst < /opt/ou/odoo.cfg.tpl > /opt/ou/odoo.cfg

click-odoo-backupdb -c "/opt/ou/odoo.cfg" --format "zip" --filestore  "$PGDATABASE" "/opt/ou/out/result.zip"
