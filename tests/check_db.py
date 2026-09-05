import os
from dotenv import load_dotenv
load_dotenv()

from src.database import get_db_connection

with get_db_connection() as conn:
    with conn.cursor() as cur:
        # Get list of all tables in public schema
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name LIKE 'test_v2_session_%';
        """)
        tables = [r[0] for r in cur.fetchall()]
        print(f"Test V2 Session Tables found ({len(tables)}):")
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            count = cur.fetchone()[0]
            cur.execute(f"SELECT metadata FROM {table} LIMIT 1;")
            meta_res = cur.fetchone()
            meta = meta_res[0] if meta_res else None
            print(f"  Table: {table} | Row Count: {count} | Sample Metadata: {meta}")
