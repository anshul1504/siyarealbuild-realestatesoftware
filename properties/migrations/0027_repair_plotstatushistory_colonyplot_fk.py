from django.db import migrations


SQL = """
PRAGMA foreign_keys=OFF;
CREATE TABLE properties_plotstatushistory_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    from_status varchar(20) NOT NULL,
    to_status varchar(20) NOT NULL,
    note varchar(240) NOT NULL,
    created_at datetime NOT NULL,
    changed_by_id INTEGER NULL REFERENCES auth_user(id) DEFERRABLE INITIALLY DEFERRED,
    plot_id INTEGER NOT NULL REFERENCES properties_colonyplot(id) DEFERRABLE INITIALLY DEFERRED
);
INSERT INTO properties_plotstatushistory_new
    (id, from_status, to_status, note, created_at, changed_by_id, plot_id)
SELECT id, from_status, to_status, note, created_at, changed_by_id, plot_id
FROM properties_plotstatushistory
WHERE plot_id IN (SELECT id FROM properties_colonyplot);
DROP TABLE properties_plotstatushistory;
ALTER TABLE properties_plotstatushistory_new RENAME TO properties_plotstatushistory;
CREATE INDEX properties_plotstatushistory_changed_by_id_idx ON properties_plotstatushistory(changed_by_id);
CREATE INDEX properties_plotstatushistory_plot_id_idx ON properties_plotstatushistory(plot_id);
PRAGMA foreign_keys=ON;
"""


class Migration(migrations.Migration):
    atomic = False
    dependencies = [("properties", "0026_plotbooking_government_id_document")]

    operations = [migrations.RunSQL(SQL, migrations.RunSQL.noop)]
