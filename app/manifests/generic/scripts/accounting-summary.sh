#!/bin/bash
set -ex

envsubst < /opt/ou/odoo.cfg.tpl > /opt/ou/odoo.cfg

SUMMARY=$(python odoo-upgrader/accounting-summary.py -c /opt/ou/odoo.cfg -d "$PGDATABASE")

if [ -f /opt/ou/data/accounting-summary ]; then
    PREV_SUMMARY=$(cat /opt/ou/data/accounting-summary)
    PREV_DIGEST=$(echo "$PREV_SUMMARY" | jq .digest)
    DIGEST=$(echo "$SUMMARY" | jq .digest)
    if [ "$DIGEST" != "$PREV_DIGEST" ]; then
        echo "Accounting data is inconsistent ($DIGEST, previous: $PREV_DIGEST)."
        diff -u <(echo "$PREV_SUMMARY" | jq .) <(echo "$SUMMARY" | jq .)
        exit 1
    fi
    echo "Accounting data is consistent. ($DIGEST, previous: $PREV_DIGEST)"
else
    echo "$SUMMARY" > /opt/ou/data/accounting-summary
fi
