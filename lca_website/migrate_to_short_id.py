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
        print("Starting database migration to 8-character short IDs...")

        projects = Project.query.all()
        project_mapping = {}

        print(f"Found {len(projects)} projects")

        for project in projects:
            old_id = project.id
            new_id = generate_short_id()

            while Project.query.get(new_id):
                new_id = generate_short_id()

            project_mapping[old_id] = new_id
            project.id = new_id
            print(f"Project '{project.name}' ID: {old_id} -> {new_id}")

        print("Updating LCA data foreign keys...")
        for lca_data in LCAData.query.all():
            if lca_data.project_id in project_mapping:
                lca_data.project_id = project_mapping[lca_data.project_id]

        print("Updating Excel file foreign keys...")
        for excel_file in ExcelFile.query.all():
            if excel_file.project_id in project_mapping:
                excel_file.project_id = project_mapping[excel_file.project_id]

        db.session.commit()
        print("Database migration complete!")

        print("\nNew project IDs:")
        for project in Project.query.all():
            print(f"- {project.name}: {project.id}")


if __name__ == "__main__":
    migrate_to_short_id()
