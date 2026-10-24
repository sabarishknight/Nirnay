"""Prints the lakehouse SQL (curated + gold) ready for `bq query`."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import lakehouse
out = []
for fn in sorted(os.listdir(lakehouse.SQL_DIR)):
    if fn[:2].isdigit() and fn.endswith(".sql"):
        out += lakehouse.render_sql(open(os.path.join(lakehouse.SQL_DIR, fn)).read(), "bigquery")
print(";\n\n".join(out) + ";")
