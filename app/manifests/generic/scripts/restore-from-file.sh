#!/bin/bash
set -ex

envsubst < odoo.cfg.tpl > odoo.cfg 

click-odoo-dropdb -c "odoo.cfg" --if-exists "$PGDATABASE"
click-odoo-restoredb -c "odoo.cfg" "$PGDATABASE" "/opt/ou/s3/object"
