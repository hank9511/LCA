import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate():

    db_paths = ["instance/lca_website.db", "lca_website.db", "database.db"]

    db_path = None
    for path in db_paths:
        if os.path.exists(path):
            db_path = path
            break

    if not db_path:
        print("❌ Database file not found")
        return False

    print(f"📊 Using database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(excel_file)")
        columns = [row[1] for row in cursor.fetchall()]

        if "metadata_json" in columns:
            print("✅ metadata_json field already exists, skipping migration")
            conn.close()
            return True

        print("📝 Adding metadata_json field to excel_file table...")
        cursor.execute(
            """
            ALTER TABLE excel_file
            ADD COLUMN metadata_json TEXT
        """
        )

        conn.commit()
        print("✅ Migration completed successfully!")

        cursor.execute("PRAGMA table_info(excel_file)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"📋 Current excel_file table columns: {', '.join(columns)}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def rollback():

    print("⚠️ SQLite does not support dropping columns directly; handle rollback manually if needed")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("Starting Excel metadata field migration")
    print("=" * 60)

    success = migrate()

    if success:
        print("\n✅ Migration succeeded!")
    else:
        print("\n❌ Migration failed!")

    print("=" * 60)
