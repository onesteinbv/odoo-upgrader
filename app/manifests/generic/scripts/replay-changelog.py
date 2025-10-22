import os
import psycopg2
import logging
from psycopg2 import sql
from json import dumps


_logger = logging.getLogger()


# NB: We're only interested in changes on website pages and blogs because the rest MUST be done automatically in the upgrade steps (OpenUpgrade) 
relevant_tables = {
    "ir_ui_view": {"fields": ["arch_db", "arch_prev", "active"], "conditions": {"type": "qweb"}},
    "website_page": {"fields": ["is_published", "active"], "conditions": {}},
    "product_template": {"fields": ["is_published", "website_description", "active"], "conditions": {}},
    "blog_post": {"fields": ["content", "is_published", "active"], "conditions": {}}
}


def _adapt(d):
    for key in d:
        if type(d[key]) is dict:
            d[key] = dumps(d[key])
    return d


def main():
    conn = psycopg2.connect()
    target_conn = psycopg2.connect(
        dbname=os.environ.get("TARGET_PGDATABASE")
    )

    cur = conn.cursor()
    select_cur = conn.cursor()
    target_cur = target_conn.cursor()
    query = sql.SQL(
        "SELECT id, table_name, operation, old, new, at FROM __changelog__ WHERE table_name IN ({relevant_tables}) ORDER BY at, id"
    ).format(relevant_tables=sql.SQL(', ').join(sql.Placeholder() * len(relevant_tables)))

    select_cur.execute(query, list(relevant_tables.keys()))
    while record := select_cur.fetchone():
        table_name, operation, old_values, new_values = record[1], record[2], record[3], record[4]

        if old_values:
            old_values = _adapt(old_values)

        if new_values:
            new_values = _adapt(new_values)

        table_identifier = sql.Identifier(table_name)
        
        if operation == "UPDATE":
            record_id = new_values.pop("id")
            query = sql.SQL("SELECT create_date FROM {table_name} WHERE id = %s").format(table_name=table_identifier)
            cur.execute(query, [record_id])
            target_cur.execute(query, [record_id])
            source_create_date = cur.fetchone()
            target_create_date = target_cur.fetchone()
            
            if not source_create_date:
                _logger.info("Source record deleted; ignore this change")
                continue
            if not target_create_date:
                _logger.info("Target record missing; ignore this change")
                continue
            source_create_date = source_create_date[0]
            target_create_date = target_create_date[0]
            if source_create_date != target_create_date:  # Not the same record
                _logger.error(
                    "Target record is not the source record (record_id = %s. source = %s, target = %s)",
                    record_id, 
                    source_create_date, 
                    target_create_date
                )
            conditions_met = True
            for field, condition in relevant_tables[table_name]["conditions"].items():
                if new_values.get(field) != condition:
                    _logger.info(
                        "Condition on field %s not met (value = %s, expected = %s); ignore this change",
                        field,
                        new_values.get(field),
                        condition
                    )
                    conditions_met = False
                    break
            if not conditions_met:
                continue

            values = {field: new_values[field] for field in relevant_tables[table_name]["fields"] if field in new_values}
            query = sql.SQL("UPDATE {table_name} SET {set} WHERE id = {id}").format(
                table_name=table_identifier,
                set=sql.SQL(", ").join([sql.SQL('{field} = {value}').format(field=sql.Identifier(key), value=sql.Placeholder()) for key in values]),
                id=sql.Placeholder()
            )
            target_cur.execute(query, list(values.values()) + [record_id])
            _logger.info("Updated record %s in table %s", record_id, table_name)
        elif operation == "DELETE":
            query = sql.SQL("DELETE FROM {table_name} WHERE id = {placeholder}").format(
                table_name=table_identifier,
                placeholder=sql.Placeholder()
            )
            target_cur.execute(query, [old_values["id"]])

    target_conn.commit()
    target_cur.close()
    target_conn.close()

    select_cur.close()
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
