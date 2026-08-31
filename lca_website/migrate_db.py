from app import app, db, ExcelFile
from datetime import datetime


def migrate_database():

    with app.app_context():

        inspector = db.inspect(db.engine)
        columns = [col["name"] for col in inspector.get_columns("excel_file")]

        print("当前ExcelFile表字段:", columns)

        if "is_deleted" not in columns:
            print("添加 is_deleted 字段...")
            db.engine.execute(
                "ALTER TABLE excel_file ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE"
            )

        if "deleted_time" not in columns:
            print("添加 deleted_time 字段...")
            db.engine.execute("ALTER TABLE excel_file ADD COLUMN deleted_time DATETIME")

        print("数据库迁移完成！")


if __name__ == "__main__":
    migrate_database()
