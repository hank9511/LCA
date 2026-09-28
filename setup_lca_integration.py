import os
import sys
import shutil


def setup_lca_integration():

    print("🔧 Setting up LCA integration environment...")

    project_root = os.path.dirname(os.path.abspath(__file__))
    lca_package_dir = os.path.join(project_root, "lca_package")
    lca_website_dir = os.path.join(project_root, "lca_website")

    print(f"📁 Project root: {project_root}")
    print(f"📁 LCA package directory: {lca_package_dir}")
    print(f"📁 Website directory: {lca_website_dir}")

    if not os.path.exists(lca_package_dir):
        print("❌ lca_package directory does not exist")
        return False

    if not os.path.exists(lca_website_dir):
        print("❌ lca_website directory does not exist")
        return False

    website_lca_package = os.path.join(lca_website_dir, "lca_package")

    if os.path.exists(website_lca_package):
        print("🗑️ Removing existing lca_package copy...")
        shutil.rmtree(website_lca_package)

    print("📋 Copying lca_package to website directory...")
    shutil.copytree(lca_package_dir, website_lca_package)

    init_file = os.path.join(website_lca_package, "__init__.py")
    if not os.path.exists(init_file):
        with open(init_file, "w") as f:
            f.write("# LCA Package\n")

    print("✅ LCA package copy complete")

    lca_service_file = os.path.join(lca_website_dir, "lca_service.py")

    with open(lca_service_file, "r", encoding="utf-8") as f:
        content = f.read()

    updated_content = content.replace(
        "from main import run_lca_analysis, create_lca_case_from_excel\n    from lca_modeler import UniversalLCAModeler",
        "from lca_package.main import run_lca_analysis, create_lca_case_from_excel\n    from lca_package.lca_modeler import UniversalLCAModeler",
    )

    with open(lca_service_file, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print("✅ lca_service.py updated")

    os.chdir(lca_website_dir)
    sys.path.insert(0, lca_website_dir)

    try:
        from lca_service import lca_service

        status = lca_service.get_system_status()
        print("✅ LCA service test succeeded")
        print(f"System status: {status}")
        return True
    except Exception as e:
        print(f"❌ LCA service test failed: {e}")
        return False


if __name__ == "__main__":
    success = setup_lca_integration()
    if success:
        print("\n🎉 LCA integration setup complete!")
        print("You can now run full LCA analysis features")
    else:
        print("\n💥 Setup failed, please check the error messages")
