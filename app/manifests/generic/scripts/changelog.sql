CREATE TABLE IF NOT EXISTS __changelog__ (
  id SERIAL PRIMARY KEY,
  table_name VARCHAR(63) NOT NULL,
  operation VARCHAR(6) NOT NULL,
  old JSONB,
  new JSONB,
  at TIMESTAMP DEFAULT now()
);
TRUNCATE __changelog__;

CREATE OR REPLACE FUNCTION __track_changes__() RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO __changelog__ (table_name, operation, new) VALUES (TG_TABLE_NAME, 'INSERT', row_to_json(NEW));
  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO __changelog__ (table_name, operation, old, new) VALUES (TG_TABLE_NAME, 'UPDATE', row_to_json(OLD), row_to_json(NEW));
  ELSIF TG_OP = 'DELETE' THEN
    INSERT INTO __changelog__ (table_name, operation, old) VALUES (TG_TABLE_NAME, 'DELETE', row_to_json(OLD));
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
  r RECORD;
  exclude VARCHAR(63)[] := array ['__changelog__'];
BEGIN
  FOR r IN SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type != 'VIEW' AND NOT (table_name = ANY(exclude)) LOOP
    EXECUTE format(
      '
        DROP TRIGGER IF EXISTS __track_changes__ ON %I;
        CREATE TRIGGER __track_changes__ AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION __track_changes__()
      ',
      r.table_name, r.table_name
    );
  END LOOP;
END $$;
