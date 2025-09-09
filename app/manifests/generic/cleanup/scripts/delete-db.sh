#!/bin/bash
set -ex

dropdb --if-exists --force "$PGDATABASE-test"
dropdb --if-exists --force "$PGDATABASE-live"
