from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from properties.models import BookingInstallment, BookingPayment


class Command(BaseCommand):
    help = "Repair local SQLite property schema drift after previously faked migrations."

    def handle(self, *args, **options):
        if connection.vendor != "sqlite":
            self.stdout.write(self.style.WARNING("This repair is only for local SQLite databases."))
            return

        cursor = connection.cursor()

        def quote(value):
            return "'" + value.replace("'", "''") + "'"

        def table_exists(table):
            return cursor.execute(
                f"SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = {quote(table)}",
            ).fetchone() is not None

        def find_latest_legacy_table(prefix):
            rows = cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE {quote(f'{prefix}_legacy_%')} ORDER BY name DESC",
            ).fetchall()
            return rows[0][0] if rows else None

        def columns(table):
            return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}

        def add_column(table, name, definition):
            if name in columns(table):
                return False
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            return True

        def drop_indexes_for_table(table):
            indexes = cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = {quote(table)}",
            ).fetchall()
            for (name,) in indexes:
                if name.startswith("sqlite_autoindex"):
                    continue
                cursor.execute(f"DROP INDEX IF EXISTS {name}")

        def table_info(table):
            return cursor.execute(f"PRAGMA table_info({table})").fetchall()

        def has_legacy_required_columns(table, model_columns):
            for row in table_info(table):
                _, name, _, notnull, default, pk = row
                if pk:
                    continue
                if name not in model_columns and notnull and default is None:
                    return True
            return False

        def rebuild_booking_installments(source_table=None):
            old_table = source_table or f"properties_bookinginstallment_legacy_{timezone.now():%Y%m%d%H%M%S}"
            cursor.execute("PRAGMA foreign_keys=OFF")
            if source_table is None:
                cursor.execute(f"ALTER TABLE properties_bookinginstallment RENAME TO {old_table}")
            drop_indexes_for_table(old_table)
            if table_exists("properties_bookinginstallment"):
                cursor.execute("DROP TABLE properties_bookinginstallment")
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(BookingInstallment)
            old_cols = columns(old_table)
            paid_expr = "paid_amount" if "paid_amount" in old_cols else "0"
            note_expr = "note" if "note" in old_cols else "''"
            updated_expr = "updated_at" if "updated_at" in old_cols else "created_at"
            cursor.execute(
                f"""
                INSERT INTO properties_bookinginstallment
                    (id, title, due_date, amount, paid_amount, status, note, created_at, updated_at, booking_id)
                SELECT id, title, due_date, amount, {paid_expr}, status, {note_expr}, created_at, {updated_expr}, booking_id
                FROM {old_table}
                """
            )
            cursor.execute("PRAGMA foreign_keys=ON")
            return old_table

        def rebuild_booking_payments(source_table=None):
            old_table = source_table or f"properties_bookingpayment_legacy_{timezone.now():%Y%m%d%H%M%S}"
            cursor.execute("PRAGMA foreign_keys=OFF")
            if source_table is None:
                cursor.execute(f"ALTER TABLE properties_bookingpayment RENAME TO {old_table}")
            drop_indexes_for_table(old_table)
            if table_exists("properties_bookingpayment"):
                cursor.execute("DROP TABLE properties_bookingpayment")
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(BookingPayment)
            old_cols = columns(old_table)
            received_on_expr = "received_on" if "received_on" in old_cols else "payment_date"
            mode_expr = "mode" if "mode" in old_cols else "payment_mode"
            reference_expr = "reference_number" if "reference_number" in old_cols else "transaction_reference"
            received_by_expr = "received_by_id" if "received_by_id" in old_cols else "posted_by_id"
            note_expr = "note" if "note" in old_cols else "''"
            installment_expr = "installment_id" if "installment_id" in old_cols else "NULL"
            cursor.execute(
                f"""
                INSERT INTO properties_bookingpayment
                    (id, received_on, amount, mode, reference_number, note, created_at, booking_id, installment_id, received_by_id)
                SELECT id, {received_on_expr}, amount, {mode_expr}, {reference_expr}, {note_expr}, created_at, booking_id, {installment_expr}, {received_by_expr}
                FROM {old_table}
                """
            )
            cursor.execute("PRAGMA foreign_keys=ON")
            return old_table

        added = []
        rebuild_missing = []
        installment_legacy = None
        payment_legacy = None
        if not table_exists("properties_bookinginstallment"):
            installment_legacy = find_latest_legacy_table("properties_bookinginstallment")
            if installment_legacy:
                rebuild_missing.append(f"properties_bookinginstallment from {installment_legacy}")
            else:
                with connection.schema_editor() as schema_editor:
                    schema_editor.create_model(BookingInstallment)
                rebuild_missing.append("properties_bookinginstallment empty")
        if not table_exists("properties_bookingpayment"):
            payment_legacy = find_latest_legacy_table("properties_bookingpayment")
            if payment_legacy:
                rebuild_missing.append(f"properties_bookingpayment from {payment_legacy}")
            else:
                with connection.schema_editor() as schema_editor:
                    schema_editor.create_model(BookingPayment)
                rebuild_missing.append("properties_bookingpayment empty")

        repairs = [
            ("properties_plotbooking", "paid_amount", "decimal NOT NULL DEFAULT 0"),
            ("properties_plotbooking", "balance_amount", "decimal NOT NULL DEFAULT 0"),
        ]
        if table_exists("properties_bookinginstallment"):
            repairs.extend(
                [
                    ("properties_bookinginstallment", "paid_amount", "decimal NOT NULL DEFAULT 0"),
                    ("properties_bookinginstallment", "note", "TEXT NOT NULL DEFAULT ''"),
                    ("properties_bookinginstallment", "updated_at", "datetime NULL"),
                ]
            )
        if table_exists("properties_bookingpayment"):
            repairs.extend(
                [
                    ("properties_bookingpayment", "installment_id", "bigint NULL REFERENCES properties_bookinginstallment(id) DEFERRABLE INITIALLY DEFERRED"),
                    ("properties_bookingpayment", "received_on", "date NULL"),
                    ("properties_bookingpayment", "mode", "varchar(30) NOT NULL DEFAULT 'cash'"),
                    ("properties_bookingpayment", "reference_number", "varchar(120) NOT NULL DEFAULT ''"),
                    ("properties_bookingpayment", "received_by_id", "integer NULL REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED"),
                    ("properties_bookingpayment", "note", "TEXT NOT NULL DEFAULT ''"),
                ]
            )
        for table, name, definition in repairs:
            if add_column(table, name, definition):
                added.append(f"{table}.{name}")

        payment_cols = columns("properties_bookingpayment")
        if {"received_on", "payment_date"}.issubset(payment_cols):
            cursor.execute("UPDATE properties_bookingpayment SET received_on = payment_date WHERE received_on IS NULL AND payment_date IS NOT NULL")
        if {"mode", "payment_mode"}.issubset(payment_cols):
            cursor.execute("UPDATE properties_bookingpayment SET mode = payment_mode WHERE payment_mode IS NOT NULL AND payment_mode != ''")
        if {"reference_number", "transaction_reference"}.issubset(payment_cols):
            cursor.execute("UPDATE properties_bookingpayment SET reference_number = transaction_reference WHERE reference_number = '' AND transaction_reference IS NOT NULL")

        rebuilt = []
        if installment_legacy:
            rebuilt.append(f"properties_bookinginstallment -> {rebuild_booking_installments(source_table=installment_legacy)}")
        if payment_legacy:
            rebuilt.append(f"properties_bookingpayment -> {rebuild_booking_payments(source_table=payment_legacy)}")
        installment_model_cols = {field.column for field in BookingInstallment._meta.local_fields}
        payment_model_cols = {field.column for field in BookingPayment._meta.local_fields}
        if table_exists("properties_bookinginstallment") and has_legacy_required_columns("properties_bookinginstallment", installment_model_cols):
            rebuilt.append(f"properties_bookinginstallment -> {rebuild_booking_installments()}")
        if table_exists("properties_bookingpayment") and has_legacy_required_columns("properties_bookingpayment", payment_model_cols):
            rebuilt.append(f"properties_bookingpayment -> {rebuild_booking_payments()}")

        connection.commit()
        if added:
            self.stdout.write(self.style.SUCCESS("Added columns: " + ", ".join(added)))
        if rebuilt:
            self.stdout.write(self.style.SUCCESS("Rebuilt legacy tables: " + ", ".join(rebuilt)))
        if rebuild_missing:
            self.stdout.write(self.style.SUCCESS("Recovered missing tables: " + ", ".join(rebuild_missing)))
        if not added and not rebuilt and not rebuild_missing:
            self.stdout.write(self.style.SUCCESS("Schema already aligned."))
