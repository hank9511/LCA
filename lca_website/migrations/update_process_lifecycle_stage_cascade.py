import sqlite3
import os
import sys
from datetime import datetime

db_path = os.path.join(os.path.dirname(__file__), "..", "instance", "lca_website.db")
db_path = os.path.abspath(db_path)


def migrate():

    print(f"开始迁移数据库: {db_path}")

    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:

        print("步骤 1: 备份现有数据...")
        cursor.execute(
            """
            CREATE TEMPORARY TABLE process_lifecycle_stage_backup AS
            SELECT * FROM process_lifecycle_stage
        """
        )

        cursor.execute("SELECT COUNT(*) FROM process_lifecycle_stage_backup")
        backup_count = cursor.fetchone()[0]
        print(f"  已备份 {backup_count} 条记录")

        print("步骤 2: 删除旧表...")
        cursor.execute("DROP TABLE IF EXISTS process_lifecycle_stage")

        print("步骤 3: 创建新表（带级联删除约束）...")
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

        print("步骤 4: 创建索引...")
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

        print("步骤 5: 恢复数据...")
        cursor.execute(
            """
            INSERT INTO process_lifecycle_stage
            SELECT * FROM process_lifecycle_stage_backup
        """
        )

        cursor.execute("SELECT COUNT(*) FROM process_lifecycle_stage")
        restored_count = cursor.fetchone()[0]
        print(f"  已恢复 {restored_count} 条记录")

        if backup_count != restored_count:
            raise Exception(
                f"数据恢复验证失败: 备份 {backup_count} 条，恢复 {restored_count} 条"
            )

        print("步骤 6: 清理临时表...")
        cursor.execute("DROP TABLE process_lifecycle_stage_backup")

        conn.commit()
        print("[OK] 迁移成功完成！")
        print(f"  处理了 {restored_count} 条记录")
        print(f"  外键约束已更新为 ON DELETE CASCADE")
        return True

    except Exception as e:
        print(f"[ERROR] 迁移失败: {str(e)}")
        conn.rollback()
        return False

    finally:
        cursor.close()
        conn.close()


def rollback():

    print("此迁移不支持自动回滚")
    print("如需回滚，请从数据库备份恢复")
    return False


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)
