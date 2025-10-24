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

    if [ -n "$CHOWN" ]; then
        echo "Transfer database ownership ...";
        psql -qc "ALTER DATABASE \"$PGDATABASE\" OWNER TO \"$CHOWN\";"
        
        echo "Transfer table, sequences and views ...";
        for pgtable in $(psql -tc "SELECT tablename FROM pg_tables WHERE schemaname = 'public'");
        do
            psql -qc "ALTER TABLE \"$pgtable\" OWNER TO \"$CHOWN\"";
        done
        for pgsequence in $(psql -tc "SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema = 'public'");
        do
            psql -qc "ALTER SEQUENCE \"$pgsequence\" OWNER TO \"$CHOWN\"";
        done
        for pgview in $(psql -tc "SELECT table_name FROM information_schema.views WHERE table_schema = 'public'");
        do
            psql -qc "ALTER VIEW \"$pgview\" OWNER TO \"$CHOWN\"";
        done
    fi
) || exit 1
