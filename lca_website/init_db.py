from app import app, db, User, Project, LCAData
from werkzeug.security import generate_password_hash
from datetime import datetime


def init_database():

    with app.app_context():

        db.create_all()
        print("Database tables created successfully!")

        if User.query.first() is None:

            admin_user = User(
                username="admin",
                email="admin@lca.com",
                password_hash=generate_password_hash("admin123"),
                created_at=datetime.utcnow(),
            )
            db.session.add(admin_user)

            sample_project = Project(
                name="Sample LCA Project",
                description="This is a sample project to demonstrate system features",
                status="active",
                user_id=1,
                created_at=datetime.utcnow(),
            )
            db.session.add(sample_project)

            sample_data = [
                LCAData(
                    project_id=1,
                    data_type="Raw material consumption",
                    value=100.0,
                    unit="kg",
                    created_at=datetime.utcnow(),
                ),
                LCAData(
                    project_id=1,
                    data_type="Energy consumption",
                    value=50.0,
                    unit="kWh",
                    created_at=datetime.utcnow(),
                ),
                LCAData(
                    project_id=1,
                    data_type="Waste generation",
                    value=10.0,
                    unit="kg",
                    created_at=datetime.utcnow(),
                ),
            ]

            for data in sample_data:
                db.session.add(data)

            db.session.commit()
            print("Initial data created successfully!")
            print("Admin account: admin / admin123")
        else:
            print("Database already has data, skipping initialization.")


if __name__ == "__main__":
    init_database()
