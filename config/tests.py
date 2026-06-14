import os
import subprocess
import sys
import tempfile
import zipfile

from django.core.management import call_command
from django.test import SimpleTestCase


class ProductionSettingsValidationTests(SimpleTestCase):
    def run_settings_import(self, **env_overrides):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("SIYA_"):
                env.pop(key)
        env.update(env_overrides)
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=os.getcwd(),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_production_rejects_debug_mode(self):
        result = self.run_settings_import(SIYA_ENV="production", SIYA_DEBUG="true")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SIYA_DEBUG must be false", result.stderr)

    def test_production_requires_database_url(self):
        result = self.run_settings_import(
            SIYA_ENV="production",
            SIYA_DEBUG="false",
            SIYA_SECRET_KEY="production-secret-value-with-enough-length",
            SIYA_ALLOWED_HOSTS="app.example.com",
            SIYA_SECURE_SSL_REDIRECT="true",
            SIYA_SESSION_COOKIE_SECURE="true",
            SIYA_CSRF_COOKIE_SECURE="true",
            SIYA_SECURE_HSTS_SECONDS="31536000",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SIYA_DATABASE_URL must point to PostgreSQL", result.stderr)

    def test_production_enabled_meta_integration_requires_secrets(self):
        result = self.run_settings_import(
            SIYA_ENV="production",
            SIYA_DEBUG="false",
            SIYA_SECRET_KEY="production-secret-value-with-enough-length",
            SIYA_ALLOWED_HOSTS="app.example.com",
            SIYA_DATABASE_URL="postgresql://user:password@localhost/siya",
            SIYA_SECURE_SSL_REDIRECT="true",
            SIYA_SESSION_COOKIE_SECURE="true",
            SIYA_CSRF_COOKIE_SECURE="true",
            SIYA_SECURE_HSTS_SECONDS="31536000",
            SIYA_META_INTEGRATION_ENABLED="true",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SIYA_META_WEBHOOK_VERIFY_TOKEN must be configured", result.stderr)


class BackupWorkspaceCommandTests(SimpleTestCase):
    databases = {"default"}

    def test_backup_workspace_creates_bundle_manifest_and_checksum(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            call_command("backup_workspace", output_dir=tmpdir, skip_media=True, verbosity=0)

            files = os.listdir(tmpdir)
            bundles = [name for name in files if name.endswith(".zip")]
            checksums = [name for name in files if name.endswith(".zip.sha256")]

            self.assertEqual(len(bundles), 1)
            self.assertEqual(len(checksums), 1)

            bundle_path = os.path.join(tmpdir, bundles[0])
            with zipfile.ZipFile(bundle_path) as archive:
                names = set(archive.namelist())
                self.assertIn("db.sqlite3", names)
                self.assertIn("manifest.json", names)
                manifest = archive.read("manifest.json").decode("utf-8")
                self.assertIn("restore_notes", manifest)
