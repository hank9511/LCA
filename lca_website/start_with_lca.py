import os
import sys


def main():
    print("=" * 60)
    print("🌍 Starting LCA integrated website")
    print("=" * 60)

    website_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(website_dir)

    print(f"📁 Working directory: {website_dir}")

    try:

        from app import app, db

        print("🔍 Checking database...")
        with app.app_context():
            db.create_all()
            print("✅ Database check complete")

        print("\n🚀 Starting website server...")
        print("📍 Website URL: http://localhost:8081")
        print("📋 Features include:")
        print("   - Excel file upload and LLM analysis")
        print("   - LCA analysis integration (Run LCA Analysis button)")
        print("   - View and manage analysis results")
        print("\n⏹️  Press Ctrl+C to stop the server")
        print("-" * 60)

        app.run(debug=True, host="0.0.0.0", port=8081)

    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except Exception as e:
        print(f"\n❌ Startup failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    success = main()
    if not success:
        print("\n💡 Please check:")
        print("   - Whether the olca_py311 environment is activated")
        print("   - Whether all dependencies are installed")
        print("   - Whether port 8081 is already in use")
        input("\nPress Enter to exit...")
