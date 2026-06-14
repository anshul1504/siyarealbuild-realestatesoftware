import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from django.utils import timezone


class Command(BaseCommand):
    help = "Create a local backup bundle for the SQLite database, media files, and deployment manifest."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="backups", help="Directory where backup bundles are written.")
        parser.add_argument("--skip-media", action="store_true", help="Do not include MEDIA_ROOT files.")

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        bundle_path = output_dir / f"siya-backup-{timestamp}.zip"
        db_settings = settings.DATABASES["default"]
        manifest = {
            "created_at": datetime.now(tz=timezone.get_current_timezone()).isoformat(),
            "environment": getattr(settings, "SIYA_ENV", "local"),
            "database_engine": db_settings.get("ENGINE", ""),
            "media_included": not options["skip_media"],
            "files": [],
            "restore_notes": [
                "Stop the application before restoring.",
                "Restore db.sqlite3 only to a matching code/migration version.",
                "Restore media/ contents after database restore.",
                "Run python manage.py check and python manage.py migrate after restore.",
            ],
        }

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if db_settings.get("ENGINE") == "django.db.backends.sqlite3":
                self._backup_sqlite_database(Path(str(db_settings["NAME"])).resolve(), archive, manifest)
            else:
                manifest["database_note"] = "Non-SQLite database detected. Use your PostgreSQL provider dump plus this media/config bundle."

            media_root = Path(settings.MEDIA_ROOT).resolve()
            if not options["skip_media"] and media_root.exists():
                self._add_directory(archive, media_root, "media", manifest)

            self._add_text(archive, "manifest.json", json.dumps(manifest, indent=2, sort_keys=True), manifest)

        digest = self._sha256(bundle_path)
        checksum_path = bundle_path.with_suffix(bundle_path.suffix + ".sha256")
        checksum_path.write_text(f"{digest}  {bundle_path.name}\n", encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Backup created: {bundle_path}"))
        self.stdout.write(self.style.SUCCESS(f"Checksum created: {checksum_path}"))

    def _backup_sqlite_database(self, db_path, archive, manifest):
        temp_path = settings.BASE_DIR / "db.sqlite3.backup-tmp"
        if temp_path.exists():
            temp_path.unlink()
        source = connections["default"]
        if not source.connection:
            source.ensure_connection()
        with source.connection:
            backup_conn = __import__("sqlite3").connect(temp_path)
            try:
                source.connection.backup(backup_conn)
            finally:
                backup_conn.close()
        try:
            self._add_file(archive, temp_path, "db.sqlite3", manifest)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _add_directory(self, archive, root, archive_root, manifest):
        for path in root.rglob("*"):
            if path.is_file():
                relative = Path(archive_root) / path.relative_to(root)
                self._add_file(archive, path, relative.as_posix(), manifest)

    def _add_file(self, archive, path, arcname, manifest):
        archive.write(path, arcname)
        manifest["files"].append(
            {
                "path": arcname,
                "size": path.stat().st_size,
                "sha256": self._sha256(path),
            }
        )

    def _add_text(self, archive, arcname, content, manifest):
        archive.writestr(arcname, content)
        manifest["files"].append(
            {
                "path": arcname,
                "size": len(content.encode("utf-8")),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        )

    def _sha256(self, path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
