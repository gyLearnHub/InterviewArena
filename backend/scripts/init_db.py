import sys
from pathlib import Path

if __package__ in {None, ""}:
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

from app.db.mysql import mysql_connection
from scripts.migrate_v1 import migrate


def main() -> None:
    sql_path = Path(__file__).resolve().parents[2] / "database" / "init_mysql.sql"
    statements = [item.strip() for item in sql_path.read_text(encoding="utf-8").split(";")]
    with mysql_connection() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                if statement:
                    cursor.execute(statement)
        migrate(connection)


if __name__ == "__main__":
    main()
