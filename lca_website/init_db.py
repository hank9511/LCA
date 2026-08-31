from app import app, db, User, Project, LCAData
from werkzeug.security import generate_password_hash
from datetime import datetime


def init_database():

    with app.app_context():

        db.create_all()
        print("数据库表创建成功！")

        if User.query.first() is None:

            admin_user = User(
                username="admin",
                email="admin@lca.com",
                password_hash=generate_password_hash("admin123"),
                created_at=datetime.utcnow(),
            )
            db.session.add(admin_user)

            sample_project = Project(
                name="示例LCA项目",
                description="这是一个示例项目，用于演示系统功能",
                status="active",
                user_id=1,
                created_at=datetime.utcnow(),
            )
            db.session.add(sample_project)

            sample_data = [
                LCAData(
                    project_id=1,
                    data_type="原材料消耗",
                    value=100.0,
                    unit="kg",
                    created_at=datetime.utcnow(),
                ),
                LCAData(
                    project_id=1,
                    data_type="能源消耗",
                    value=50.0,
                    unit="kWh",
                    created_at=datetime.utcnow(),
                ),
                LCAData(
                    project_id=1,
                    data_type="废弃物产生",
                    value=10.0,
                    unit="kg",
                    created_at=datetime.utcnow(),
                ),
            ]

            for data in sample_data:
                db.session.add(data)

            db.session.commit()
            print("初始数据创建成功！")
            print("管理员账户: admin / admin123")
        else:
            print("数据库已存在数据，跳过初始化。")


if __name__ == "__main__":
    init_database()
