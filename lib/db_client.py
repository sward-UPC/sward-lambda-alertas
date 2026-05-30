from contextlib import contextmanager


@contextmanager
def get_connection(database_url: str):
    """Conexión psycopg2 directa (no ORM) para uso en Lambda, parametrizada por URL."""
    try:
        import psycopg2
    except ImportError:
        raise RuntimeError(
            "psycopg2 no disponible. Incluirlo en requirements.txt del Lambda."
        )

    conn = psycopg2.connect(database_url)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
