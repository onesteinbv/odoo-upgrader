#!/bin/bash

envsubst < /opt/ou/odoo.cfg.tpl > /opt/ou/odoo.cfg

DIGEST=$(python odoo-upgrader/accounting-summary.py -c /opt/ou/odoo.cfg -d "$PGDATABASE" --digest)

if [ -f /opt/ou/data/accounting-summary-digest ]; then
    PREV_DIGEST=$(cat /opt/ou/data/accounting-summary-digest)
    if [ "$DIGEST" != "$PREV_DIGEST" ]; then
        echo "Accounting data is inconsistent ($DIGEST, previous: $PREV_DIGEST)."
        exit 1
    fi
    echo "Accounting data is consistent. ($DIGEST, previous: $PREV_DIGEST)"
else
    echo "$DIGEST" > /opt/ou/data/accounting-summary-digest
fi
