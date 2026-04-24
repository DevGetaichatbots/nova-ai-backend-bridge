import logging
import threading
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values
from psycopg2 import sql
from psycopg2 import pool as pg_pool

logger = logging.getLogger(__name__)
from contextlib import contextmanager
from urllib.parse import urlparse, unquote
import re
from src.config import settings, get_database_url

_connection_pool = None
_pool_lock = threading.Lock()


def sanitize_table_name(name: str) -> str:
    sanitized = name.replace("-", "_").replace(" ", "_").replace(".", "_")
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', sanitized)
    if sanitized and sanitized[0].isdigit():
        sanitized = "t_" + sanitized
    sanitized = sanitized[:63]
    if not sanitized:
        raise ValueError("Invalid table name: results in empty string after sanitization")
    return sanitized.lower()


def parse_database_url(url: str) -> dict:
    if not url:
        return {}
    
    try:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        
        at_idx = url.rfind('@')
        if at_idx == -1:
            return {}
        
        credentials_part = url[len("postgresql://"):at_idx]
        host_part = url[at_idx + 1:]
        
        if ':' in credentials_part:
            user, password = credentials_part.split(':', 1)
        else:
            user = credentials_part
            password = ""
        
        if '/' in host_part:
            host_and_port, database = host_part.split('/', 1)
            database = database.split('?')[0]
        else:
            host_and_port = host_part
            database = "postgres"
        
        if ':' in host_and_port:
            host, port = host_and_port.rsplit(':', 1)
            port = int(port)
        else:
            host = host_and_port
            port = 5432
        
        return {
            "host": host,
            "port": port,
            "database": database,
            "user": unquote(user),
            "password": unquote(password)
        }
    except Exception as e:
        print(f"Error parsing database URL: {e}")
        return {}


def _get_pool():
    global _connection_pool
    if _connection_pool is not None:
        return _connection_pool
    with _pool_lock:
        if _connection_pool is not None:
            return _connection_pool
        db_url = get_database_url()
        parsed = parse_database_url(db_url) if db_url else {}
        
        if parsed:
            _connection_pool = pg_pool.ThreadedConnectionPool(
                minconn=2, maxconn=8,
                host=parsed["host"],
                port=parsed["port"],
                database=parsed["database"],
                user=parsed["user"],
                password=parsed["password"],
                sslmode="require"
            )
        else:
            _connection_pool = pg_pool.ThreadedConnectionPool(
                minconn=2, maxconn=8,
                host=settings.SUPABASE_DB_HOST,
                port=settings.SUPABASE_DB_PORT,
                database=settings.SUPABASE_DB_NAME,
                user=settings.SUPABASE_DB_USER,
                password=settings.SUPABASE_DB_PASSWORD,
                sslmode="require"
            )
    return _connection_pool


@contextmanager
def get_db_connection():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def init_pgvector_extension():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()


def create_vector_table(table_name: str, dimension: int = 1536):
    safe_table_name = sanitize_table_name(table_name)
    index_name = f"{safe_table_name}_embedding_idx"
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            create_table_query = sql.SQL("""
                CREATE TABLE IF NOT EXISTS {table} (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    embedding vector({dim}),
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """).format(
                table=sql.Identifier(safe_table_name),
                dim=sql.Literal(dimension)
            )
            cur.execute(create_table_query)
            
            create_index_query = sql.SQL("""
                CREATE INDEX IF NOT EXISTS {index} 
                ON {table} USING hnsw (embedding vector_cosine_ops)
            """).format(
                index=sql.Identifier(index_name),
                table=sql.Identifier(safe_table_name)
            )
            cur.execute(create_index_query)
            
            conn.commit()
    
    return safe_table_name


def insert_embeddings(table_name: str, documents: list):
    safe_table_name = sanitize_table_name(table_name)
    
    BATCH_SIZE = 100
    
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(documents), BATCH_SIZE):
                batch_docs = documents[i:i + BATCH_SIZE]
                batch_values = []
                for doc in batch_docs:
                    embedding_str = "[" + ",".join(map(str, doc["embedding"])) + "]"
                    batch_values.append((doc["content"], embedding_str, doc.get("metadata", "{}")))
                
                execute_values(
                    cur,
                    sql.SQL("INSERT INTO {table} (content, embedding, metadata) VALUES %s").format(
                        table=sql.Identifier(safe_table_name)
                    ).as_string(conn),
                    batch_values,
                    template="(%s, %s::vector, %s::jsonb)",
                    page_size=BATCH_SIZE
                )
                batch_num = i // BATCH_SIZE + 1
                logger.info(f"  Inserted batch {batch_num} ({len(batch_docs)} chunks)")
            
            conn.commit()


def similarity_search(table_name: str, query_embedding: list, top_k: int = 5):
    safe_table_name = sanitize_table_name(table_name)
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            search_query = sql.SQL("""
                SELECT 
                    id,
                    content,
                    metadata,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {table}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """).format(table=sql.Identifier(safe_table_name))
            
            cur.execute(search_query, (embedding_str, embedding_str, top_k))
            results = cur.fetchall()
    
    return results


def fetch_all_chunks(table_name: str, chunk_type: str = None) -> list:
    safe_table_name = sanitize_table_name(table_name)
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if chunk_type:
                query = sql.SQL("""
                    SELECT id, content, metadata
                    FROM {table}
                    WHERE metadata->>'type' = %s
                    ORDER BY id ASC
                """).format(table=sql.Identifier(safe_table_name))
                cur.execute(query, (chunk_type,))
            else:
                query = sql.SQL("""
                    SELECT id, content, metadata
                    FROM {table}
                    ORDER BY id ASC
                """).format(table=sql.Identifier(safe_table_name))
                cur.execute(query)
            
            results = cur.fetchall()
    
    return [
        {
            "content": r["content"],
            "similarity": 1.0,
            "metadata": r["metadata"] if r["metadata"] else {}
        }
        for r in results
    ]


def create_chat_memory_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS chat_memory (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                
                CREATE INDEX IF NOT EXISTS chat_memory_session_idx 
                ON chat_memory(session_id);

                CREATE TABLE IF NOT EXISTS session_metadata (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) NOT NULL,
                    old_filename VARCHAR(500),
                    new_filename VARCHAR(500),
                    old_table_name VARCHAR(255),
                    new_table_name VARCHAR(255),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS session_metadata_idx
                ON session_metadata(session_id);
            """)
            conn.commit()


def save_session_metadata(session_id: str, old_filename: str, new_filename: str, old_table_name: str, new_table_name: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO session_metadata (session_id, old_filename, new_filename, old_table_name, new_table_name)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (session_id, old_filename, new_filename, old_table_name, new_table_name))
            conn.commit()


def get_session_metadata(session_id: str) -> dict:
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT old_filename, new_filename, old_table_name, new_table_name
                FROM session_metadata
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (session_id,))
            result = cur.fetchone()
    return dict(result) if result else {}


def save_chat_message(session_id: str, role: str, content: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_memory (session_id, role, content)
                VALUES (%s, %s, %s)
            """, (session_id, role, content))
            conn.commit()


def get_chat_history(session_id: str, limit: int = 10):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT role, content, created_at
                FROM chat_memory
                WHERE session_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (session_id, limit))
            
            results = cur.fetchall()
    
    return list(reversed(results))
