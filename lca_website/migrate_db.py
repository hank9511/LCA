from app import app, db, ExcelFile
from datetime import datetime


def migrate_database():

    with app.app_context():

        inspector = db.inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns("excel_file")]

        print("Current ExcelFile table columns:", columns)

        if "is_deleted" not in columns:
            print("Adding is_deleted field...")
            db.engine.execute(
                "ALTER TABLE excel_file ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"
            )

        if "deleted_time" not in columns:
            print("Adding deleted_time field...")
            db.engine.execute("ALTER TABLE excel_file ADD COLUMN deleted_time DATETIME")

        print("Database migration complete!")


if __name__ == "__main__":
    migrate_database()
