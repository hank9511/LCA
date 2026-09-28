import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app import app, db, ProjectReportInfo


def migrate_ipcc_method():

    with app.app_context():
        print("=" * 80)
        print("🔄 Starting migration: update LCIA impact assessment method")
        print("=" * 80)
        print(f"From: ecoinvent - IPCC 2021 no LT")
        print(f"To: ecoinvent - IPCC 2021")
        print("-" * 80)

        try:

            old_method = "ecoinvent - IPCC 2021 no LT"
            new_method = "ecoinvent - IPCC 2021"

            projects_to_update = ProjectReportInfo.query.filter_by(
                standard_used=old_method
            ).all()

            if not projects_to_update:
                print("✅ No projects need updating (all already use the new method or other methods)")

                all_projects = ProjectReportInfo.query.all()
                if all_projects:
                    print(f"\n📊 Current projects in database: {len(all_projects)}")
                    methods_used = {}
                    for project in all_projects:
                        method = project.standard_used or "Not set"
                        methods_used[method] = methods_used.get(method, 0) + 1

                    print("\n📋 Impact assessment method usage:")
                    for method, count in methods_used.items():
                        print(f"   - {method}: {count} projects")
                else:
                    print("\n📊 No projects in the database yet")

                return

            print(f"\n🔍 Found {len(projects_to_update)} projects using the old method that need updating:\n")

            for idx, project in enumerate(projects_to_update, 1):
                print(f"   {idx}. Project ID: {project.project_id}")
                print(f"      Product name: {project.product_name or 'Not set'}")
                print(f"      Current method: {project.standard_used}")
                print()

            response = input("⚠️  Confirm updating these projects? (y/n): ").strip().lower()

            if response != "y":
                print("❌ Update cancelled")
                return

            print("\n🔄 Starting update...")
            updated_count = 0

            for project in projects_to_update:
                project.standard_used = new_method
                updated_count += 1
                print(
                    f"   ✅ Updated project: {project.project_id} - {project.product_name or 'Unnamed'}"
                )

            db.session.commit()

            print(f"\n✅ Migration complete!")
            print(f"   - Successfully updated {updated_count} projects")
            print(f"   - New impact assessment method: {new_method}")
            print("\n💡 Tips:")
            print("   - Please re-run LCA analysis to use the new impact assessment method")
            print("   - The new method includes long-term climate impact factors; results may differ")

        except Exception as e:
            print(f"\n❌ Migration failed: {str(e)}")
            db.session.rollback()
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    migrate_ipcc_method()
