import os
import uuid
from app import app, db, Project, LCAData, ExcelFile


def migrate_to_uuid():

    with app.app_context():
        print("Starting database migration to UUID...")

        projects = Project.query.all()
        project_mapping = {}

        print(f"Found {len(projects)} projects")

        for project in projects:
            old_id = project.id
            new_id = str(uuid.uuid4())
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
    migrate_to_uuid()
