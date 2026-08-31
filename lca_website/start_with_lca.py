import os
import sys


def main():
    print("=" * 60)
    print("🌍 启动LCA集成网站")
    print("=" * 60)

    website_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(website_dir)

    print(f"📁 工作目录: {website_dir}")

    try:

        from app import app, db

        print("🔍 检查数据库...")
        with app.app_context():
            db.create_all()
            print("✅ 数据库检查完成")

        print("\n🚀 启动网站服务器...")
        print("📍 网站地址: http://localhost:8081")
        print("📋 功能包括:")
        print("   - Excel文件上传和LLM分析")
        print("   - LCA分析集成 (运行LCA分析按钮)")
        print("   - 分析结果查看和管理")
        print("\n⏹️  按 Ctrl+C 停止服务器")
        print("-" * 60)

        app.run(debug=True, host="0.0.0.0", port=8081)

    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = main()
    if not success:
        print("\n💡 请检查:")
        print("   - 是否已激活 olca_py311 环境")
        print("   - 是否已安装所有依赖包")
        print("   - 端口8081是否被占用")
        input("\n按回车键退出...")
