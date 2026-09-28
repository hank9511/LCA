import sqlite3
import os
import sys
from datetime import datetime

db_path = os.path.join(os.path.dirname(__file__), "..", "instance", "lca_website.db")
db_path = os.path.abspath(db_path)


def migrate():

    print(f"Starting database migration: {db_path}")

    if not os.path.exists(db_path):
        print(f"Error: database file does not exist: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:

        print("Step 1: Backing up existing data...")
        cursor.execute(
            """
            CREATE TEMPORARY TABLE process_lifecycle_stage_backup AS
            SELECT * FROM process_lifecycle_stage
        """
        )

        cursor.execute("SELECT COUNT(*) FROM process_lifecycle_stage_backup")
        backup_count = cursor.fetchone()[0]
        print(f"  Backed up {backup_count} records")

        print("Step 2: Dropping old table...")
        cursor.execute("DROP TABLE IF EXISTS process_lifecycle_stage")

        print("Step 3: Creating new table (with cascade delete constraint)...")
        cursor.execute(
            """
            CREATE TABLE process_lifecycle_stage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                excel_file_id INTEGER NOT NULL,
                process_name TEXT NOT NULL,
                lifecycle_stage TEXT NOT NULL,
                is_auto_matched BOOLEAN DEFAULT 1,
                confidence_score REAL,
                llm_reasoning TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (excel_file_id) REFERENCES excel_file (id) ON DELETE CASCADE
            )
        """
        )

        print("Step 4: Creating indexes...")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_process_lifecycle_excel_file_id
            ON process_lifecycle_stage(excel_file_id)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_process_lifecycle_process_name
            ON process_lifecycle_stage(process_name)
        """
        )

        print("Step 5: Restoring data...")
        cursor.execute(
            """
            INSERT INTO process_lifecycle_stage
            SELECT * FROM process_lifecycle_stage_backup
        """
        )

        cursor.execute("SELECT COUNT(*) FROM process_lifecycle_stage")
        restored_count = cursor.fetchone()[0]
        print(f"  Restored {restored_count} records")

        if backup_count != restored_count:
            raise Exception(
                f"Data restore verification failed: backed up {backup_count}, restored {restored_count}"
            )

        print("Step 6: Cleaning up temporary table...")
        cursor.execute("DROP TABLE process_lifecycle_stage_backup")

        conn.commit()
        print("[OK] Migration completed successfully!")
        print(f"  Processed {restored_count} records")
        print(f"  Foreign key constraint updated to ON DELETE CASCADE")
        return True

    except Exception as e:
        print(f"[ERROR] Migration failed: {str(e)}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()


def rollback():

    print("This migration does not support automatic rollback")
    print("To roll back, please restore from a database backup")
    return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
