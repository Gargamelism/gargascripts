import sqlite3


class SqliteWrapper:
    def __init__(self, db_name):
        self._db = sqlite3.connect(db_name)
        self._cursor = self._db.cursor()

    def create_table(self, table_name, columns):
        self._cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {', '.join(columns)}
            )
            """
        )
        self._db.commit()

    def insert(self, table_name, values):
        self._cursor.execute(
            f"""
            INSERT INTO {table_name} VALUES ({', '.join(['?' for _ in values])})
            """,
            values,
        )
        self._db.commit()

    def insert_many(self, table_name, values):
        self._cursor.executemany(
            f"""
            INSERT INTO {table_name} VALUES ({', '.join(['?' for _ in values[0]])})
            """,
            values,
        )
        self._db.commit()

    def paginate(self, table_name, page_size, page_number):
        return self._cursor.execute(
            f"""
            SELECT * FROM {table_name}
            LIMIT {page_size} OFFSET {page_number * page_size}
            """
        ).fetchall()

    def count(self, table_name):
        return self._cursor.execute(
            f"""
            SELECT COUNT(*) FROM {table_name}
            """
        ).fetchone()[0]

    def close(self):
        self._cursor.close()
        self._db.close()
