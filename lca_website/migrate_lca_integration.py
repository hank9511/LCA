"""Database migration script for LCA integration"""

import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from app import app, db


def migrate_database():
    """Migrate database to add LCA integration features"""

    print("🔄 开始数据库迁移...")

    with app.app_context():
        try:

            print("📊 创建LCAResult表...")

            from sqlalchemy import inspect

            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()

            if "lca_result" in existing_tables:
                print("⚠️ LCAResult表已存在，跳过创建")
            else:

                from app import LCAResult

                db.create_all()
                print("✅ LCAResult表创建成功")

            excel_file_columns = [
                col["name"] for col in inspector.get_columns("excel_file")
            ]
            print(f"📋 ExcelFile表当前列: {excel_file_columns}")

            print("✅ 数据库迁移完成!")
            print("\n🎉 LCA集成功能已准备就绪！")
            print("\n📖 使用说明:")
            print("1. 确保openLCA正在运行")
            print("2. 在openLCA中启用IPC服务器（开发者工具 → IPC服务器）")
            print("3. 设置IPC服务器端口为8080")
            print("4. 在网站项目详情页面点击'运行LCA分析'按钮")
            print("5. 查看分析结果和详细信息")

        except Exception as e:
            print(f"❌ 数据库迁移失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    return True


if __name__ == "__main__":
    success = migrate_database()
    if success:
        print("\n🚀 迁移成功！现在可以使用LCA分析功能了。")
    else:
        print("\n💥 迁移失败！请检查错误信息并重试。")
