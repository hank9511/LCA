import os
import sys
import shutil


def setup_lca_integration():

    print("🔧 设置LCA集成环境...")

    project_root = os.path.dirname(os.path.abspath(__file__))
    lca_package_dir = os.path.join(project_root, "lca_package")
    lca_website_dir = os.path.join(project_root, "lca_website")

    print(f"📁 项目根目录: {project_root}")
    print(f"📁 LCA包目录: {lca_package_dir}")
    print(f"📁 网站目录: {lca_website_dir}")

    if not os.path.exists(lca_package_dir):
        print("❌ lca_package目录不存在")
        return False

    if not os.path.exists(lca_website_dir):
        print("❌ lca_website目录不存在")
        return False

    website_lca_package = os.path.join(lca_website_dir, "lca_package")

    if os.path.exists(website_lca_package):
        print("🗑️ 删除现有的lca_package副本...")
        shutil.rmtree(website_lca_package)

    print("📋 复制lca_package到网站目录...")
    shutil.copytree(lca_package_dir, website_lca_package)

    init_file = os.path.join(website_lca_package, "__init__.py")
    if not os.path.exists(init_file):
        with open(init_file, "w") as f:
            f.write("# LCA Package\n")

    print("✅ LCA包复制完成")

    lca_service_file = os.path.join(lca_website_dir, "lca_service.py")

    with open(lca_service_file, "r", encoding="utf-8") as f:
        content = f.read()

    updated_content = content.replace(
        "from main import run_lca_analysis, create_lca_case_from_excel\n    from lca_modeler import UniversalLCAModeler",
        "from lca_package.main import run_lca_analysis, create_lca_case_from_excel\n    from lca_package.lca_modeler import UniversalLCAModeler",
    )

    with open(lca_service_file, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print("✅ lca_service.py已更新")

    os.chdir(lca_website_dir)
    sys.path.insert(0, lca_website_dir)

    try:
        from lca_service import lca_service

        status = lca_service.get_system_status()
        print("✅ LCA服务测试成功")
        print(f"系统状态: {status}")
        return True
    except Exception as e:
        print(f"❌ LCA服务测试失败: {e}")
        return False


if __name__ == "__main__":
    success = setup_lca_integration()
    if success:
        print("\n🎉 LCA集成设置完成！")
        print("现在可以运行完整的LCA分析功能")
    else:
        print("\n💥 设置失败，请检查错误信息")
