import os
import random
import string
from app import app, db, Project, LCAData, ExcelFile


def generate_short_id():

    chars = string.ascii_uppercase.replace("O", "").replace(
        "I", ""
    ) + string.digits.replace("0", "").replace("1", "")
    return "".join(random.choice(chars) for _ in range(8))


def migrate_to_short_id():

    with app.app_context():
        print("开始迁移数据库到8位短ID...")

        projects = Project.query.all()
        project_mapping = {}

        print(f"找到 {len(projects)} 个项目")

        for project in projects:
            old_id = project.id
            new_id = generate_short_id()

            while Project.query.get(new_id):
                new_id = generate_short_id()

            project_mapping[old_id] = new_id
            project.id = new_id
            print(f"项目 '{project.name}' ID: {old_id} -> {new_id}")

        print("更新LCA数据外键...")
        for lca_data in LCAData.query.all():
            if lca_data.project_id in project_mapping:
                lca_data.project_id = project_mapping[lca_data.project_id]

        print("更新Excel文件外键...")
        for excel_file in ExcelFile.query.all():
            if excel_file.project_id in project_mapping:
                excel_file.project_id = project_mapping[excel_file.project_id]

        db.session.commit()
        print("数据库迁移完成！")

        print("\n新的项目ID:")
        for project in Project.query.all():
            print(f"- {project.name}: {project.id}")


if __name__ == "__main__":
    migrate_to_short_id()
