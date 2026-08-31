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
        print("❌ 未找到数据库文件")
        return False

    print(f"📊 使用数据库: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(excel_file)")
        columns = [row[1] for row in cursor.fetchall()]

        if "metadata_json" in columns:
            print("✅ metadata_json字段已存在，跳过迁移")
            conn.close()
            return True

        print("📝 添加metadata_json字段到excel_file表...")
        cursor.execute(
            """
            ALTER TABLE excel_file
            ADD COLUMN metadata_json TEXT
        """
        )

        conn.commit()
        print("✅ 迁移成功完成！")

        cursor.execute("PRAGMA table_info(excel_file)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"📋 当前excel_file表字段: {', '.join(columns)}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False


def rollback():

    print("⚠️ SQLite不支持直接删除列，如需回滚请手动处理")
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("开始执行Excel元数据字段迁移")
    print("=" * 60)

    success = migrate()

    if success:
        print("\n✅ 迁移成功！")
    else:
        print("\n❌ 迁移失败！")

    print("=" * 60)
