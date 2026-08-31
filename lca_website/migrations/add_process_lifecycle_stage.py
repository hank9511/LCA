import sqlite3
import os


def migrate():

    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "instance", "lca_website.db"
    )

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS process_lifecycle_stage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                excel_file_id INTEGER NOT NULL,
                process_name VARCHAR(500) NOT NULL,
                lifecycle_stage VARCHAR(100) NOT NULL,
                is_auto_matched BOOLEAN DEFAULT 1,
                confidence_score FLOAT,
                llm_reasoning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (excel_file_id) REFERENCES excel_file (id)
            )
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_process_lifecycle_excel_file
            ON process_lifecycle_stage(excel_file_id)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_process_lifecycle_process_name
            ON process_lifecycle_stage(process_name)
        """
        )

        conn.commit()
        print("[OK] Successfully created process_lifecycle_stage table and indexes")

    except sqlite3.Error as e:
        print(f"[ERROR] Database migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
