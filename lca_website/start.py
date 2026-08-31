import subprocess
import sys
import os


def run_command(command, description, cwd=None):

    print(f"\n{description}...")
    print(f"执行命令: {command}")
    if cwd:
        print(f"工作目录: {cwd}")

    try:
        result = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True, cwd=cwd
        )
        print("✓ 成功")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 失败: {e}")
        if e.stderr:
            print(f"错误信息: {e.stderr}")
        return False


def main():

    print("🚀 启动LCA服务网站")
    print("=" * 50)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"脚本目录: {script_dir}")

    app_file = os.path.join(script_dir, "app.py")
    if not os.path.exists(app_file):
        print(f"❌ 错误: 找不到 app.py 文件")
        print(f"期望路径: {app_file}")
        return False

    print(f"✅ 找到 app.py 文件: {app_file}")

    print(f"Python版本: {sys.version}")

    print("\n📦 安装Python依赖包...")
    dependencies = [
        "flask",
        "flask-sqlalchemy",
        "flask-login",
        "werkzeug",
        "pandas",
        "openpyxl",
        "openai",
    ]

    for dep in dependencies:
        if not run_command(f"pip install {dep}", f"安装 {dep}"):
            print(f"❌ 安装 {dep} 失败，请检查网络连接或手动安装")
            return False

    print("\n✅ 所有依赖安装完成！")

    print("\n🌐 启动网站...")
    if not run_command("python app.py", "启动Flask应用", cwd=script_dir):
        print("❌ 启动应用失败")
        return False

    return True


if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n🎉 网站启动成功！")
        else:
            print("\n💥 启动过程中遇到问题")
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断操作")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")

    input("\n按回车键退出...")
