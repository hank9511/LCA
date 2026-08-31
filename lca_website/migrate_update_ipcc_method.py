import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import app, db, ProjectReportInfo


def migrate_ipcc_method():

    with app.app_context():
        print("=" * 80)
        print("🔄 开始迁移：更新LCIA影响评价方法")
        print("=" * 80)
        print(f"从: ecoinvent - IPCC 2021 no LT")
        print(f"到: ecoinvent - IPCC 2021")
        print("-" * 80)

        try:

            old_method = "ecoinvent - IPCC 2021 no LT"
            new_method = "ecoinvent - IPCC 2021"

            projects_to_update = ProjectReportInfo.query.filter_by(
                standard_used=old_method
            ).all()

            if not projects_to_update:
                print("✅ 没有需要更新的项目（所有项目已使用新方法或使用其他方法）")

                all_projects = ProjectReportInfo.query.all()
                if all_projects:
                    print(f"\n📊 当前数据库中的项目数: {len(all_projects)}")
                    methods_used = {}
                    for project in all_projects:
                        method = project.standard_used or "未设置"
                        methods_used[method] = methods_used.get(method, 0) + 1

                    print("\n📋 各影响评价方法使用情况:")
                    for method, count in methods_used.items():
                        print(f"   - {method}: {count} 个项目")
                else:
                    print("\n📊 数据库中暂无项目")

                return

            print(f"\n🔍 找到 {len(projects_to_update)} 个使用旧方法的项目需要更新:\n")

            for idx, project in enumerate(projects_to_update, 1):
                print(f"   {idx}. 项目ID: {project.project_id}")
                print(f"      产品名称: {project.product_name or '未设置'}")
                print(f"      当前方法: {project.standard_used}")
                print()

            response = input("⚠️  确认要更新这些项目吗？(y/n): ").strip().lower()

            if response != "y":
                print("❌ 取消更新")
                return

            print("\n🔄 开始更新...")
            updated_count = 0

            for project in projects_to_update:
                project.standard_used = new_method
                updated_count += 1
                print(
                    f"   ✅ 已更新项目: {project.project_id} - {project.product_name or '未命名'}"
                )

            db.session.commit()

            print(f"\n✅ 迁移完成！")
            print(f"   - 成功更新 {updated_count} 个项目")
            print(f"   - 新的影响评价方法: {new_method}")
            print("\n💡 提示:")
            print("   - 请重新运行LCA分析以使用新的影响评价方法")
            print("   - 新方法包含长期气候影响因子，结果可能会有所不同")

        except Exception as e:
            print(f"\n❌ 迁移失败: {str(e)}")
            db.session.rollback()
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    migrate_ipcc_method()
