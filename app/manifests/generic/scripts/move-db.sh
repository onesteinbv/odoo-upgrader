#!/bin/bash
set -e

mkdir /opt/ou/out

envsubst < odoo.cfg.tpl > odoo.cfg
click-odoo-backupdb -c "odoo.cfg" --format "zip" --filestore "$PGDATABASE" "/opt/ou/out/result.zip"

(
    set -e
    export PGHOST=$TARGET_PGHOST
    export PGPORT=$TARGET_PGPORT
    export PGUSER=$TARGET_PGUSER
    export PGPASSWORD=$TARGET_PGPASSWORD
    export PGDATABASE=$TARGET_PGDATABASE

    envsubst < odoo.cfg.tpl > odoo.cfg
    click-odoo-dropdb -c "odoo.cfg" --if-exists "$PGDATABASE"
    click-odoo-restoredb -c "odoo.cfg" "$PGDATABASE" "/opt/ou/out/result.zip"
) || exit 1
