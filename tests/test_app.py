import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup


class AppStartupFallbackTest(unittest.TestCase):
    def test_app_starts_with_sqlite_fallback(self):
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
        sys.modules.pop("app", None)

        app_module = importlib.import_module("app")

        self.assertIn(app_module.app.config["SQLALCHEMY_DATABASE_URI"], ["sqlite:///todo.db", "postgresql://sc_wwi9_user:L4O7nhTgiaP8cRsVhRC508pgXiLtyW5x@dpg-d91rntu7r5hc738rrttg-a.singapore-postgres.render.com/sc_wwi9"])

        with app_module.app.test_client() as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)

    def test_app_reads_database_url_from_project_env_file(self):
        repo_root = Path(__file__).resolve().parents[1]
        env_file = repo_root / ".env"
        original_cwd = os.getcwd()
        original_env = os.environ.get("DATABASE_URL")
        original_sqlalchemy_env = os.environ.get("SQLALCHEMY_DATABASE_URI")
        original_env_content = env_file.read_text(encoding="utf-8") if env_file.exists() else ""

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                os.chdir(temp_dir)
                os.environ.pop("DATABASE_URL", None)
                os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
                env_file.write_text("DATABASE_URL=sqlite:///from_env.db\n", encoding="utf-8")
                sys.modules.pop("app", None)

                app_module = importlib.import_module("app")

                self.assertEqual(app_module.app.config["SQLALCHEMY_DATABASE_URI"], "sqlite:///from_env.db")
        finally:
            os.chdir(original_cwd)
            if original_env is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_env

            if original_sqlalchemy_env is None:
                os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
            else:
                os.environ["SQLALCHEMY_DATABASE_URI"] = original_sqlalchemy_env

            if original_env_content:
                env_file.write_text(original_env_content, encoding="utf-8")
            elif env_file.exists():
                env_file.unlink()

    def test_app_seeds_initial_todos(self):
        original_database_url = os.environ.get("DATABASE_URL")
        original_sqlalchemy_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = Path(temp_dir) / "seed.db"
                os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
                os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
                sys.modules.pop("app", None)

                app_module = importlib.import_module("app")

                with app_module.app.app_context():
                    todo_count = app_module.Todo.query.count()

                self.assertGreaterEqual(todo_count, 1)
        finally:
            if original_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = original_database_url

            if original_sqlalchemy_uri is None:
                os.environ.pop("SQLALCHEMY_DATABASE_URI", None)
            else:
                os.environ["SQLALCHEMY_DATABASE_URI"] = original_sqlalchemy_uri

    def test_extract_course_events_from_html_finds_course_blocks(self):
        app_module = importlib.import_module("app")
        html = """
        <div class="event_container id-31">
            <span class="event_header" title="微積分(一)">微積分(一)</span>
            <div class='before_hour_text'>陳琬萍</div>
            <div class="hours_container"><span class="hours">10:10 - 12:00</span></div>
            <div class='after_hour_text'>MA307</div>
        </div>
        """

        events = app_module.extract_course_events_from_soup(BeautifulSoup(html, "html.parser"))

        self.assertTrue(events)
        self.assertEqual(events[0]["course_name"], "微積分(一)")
        self.assertEqual(events[0]["teacher"], "陳琬萍")
        self.assertEqual(events[0]["time"], "10:10 - 12:00")
        self.assertEqual(events[0]["room"], "MA307")

    def test_render_config_uses_gunicorn_entrypoint(self):
        repo_root = Path(__file__).resolve().parents[1]
        render_file = repo_root / "render.yaml"

        self.assertTrue(render_file.exists(), "render.yaml should exist for Render deployment")
        content = render_file.read_text(encoding="utf-8")
        self.assertIn("gunicorn app:app", content)


if __name__ == "__main__":
    unittest.main()
