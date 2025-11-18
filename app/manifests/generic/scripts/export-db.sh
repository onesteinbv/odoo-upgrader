#!/bin/bash
set -ex

envsubst < odoo.cfg.tpl > odoo.cfg

# Export DB
mkdir /opt/ou/out

if [ -n "$FILESTORE" ] && [ "$FILESTORE" = "true" ]; then
    click-odoo-backupdb -c "/opt/ou/odoo.cfg" --format "zip" --filestore  "$PGDATABASE" "/opt/ou/out/result.zip"
else
    click-odoo-backupdb -c "/opt/ou/odoo.cfg" --format "zip" --no-filestore  "$PGDATABASE" "/opt/ou/out/result.zip"
fi
