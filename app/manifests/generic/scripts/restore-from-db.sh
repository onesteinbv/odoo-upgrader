#!/bin/bash

mkdir /opt/ou/out

(
    export PGHOST=$TARGET_PGHOST
    export PGPORT=$TARGET_PGPORT
    export PGUSER=$TARGET_PGUSER
    export PGPASSWORD=$TARGET_PGPASSWORD
    export PGDATABASE=$TARGET_PGDATABASE

    envsubst < odoo.cfg.tpl > odoo.cfg
    click-odoo-backupdb -c "odoo.cfg" --format "zip" --no-filestore "$PGDATABASE" "/opt/ou/out/result.zip"
) || exit 1

set -ex


envsubst < odoo.cfg.tpl > odoo.cfg 

click-odoo-dropdb -c "odoo.cfg" --if-exists "$PGDATABASE"
click-odoo-restoredb -c "odoo.cfg" "$PGDATABASE" "/opt/ou/out/result.zip"
