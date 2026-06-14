from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from anchor.adapters.sqlite_links_repository import SqliteLinksRepository
from anchor.adapters.sqlite_migration_repository import SqliteMigrationRepository
from anchor.application.links.service import DocumentLinksService
from anchor.application.system.metadata_service import MetadataSchemaService
from anchor.config import LinksConfig, MetadataConfig, MetadataEntityConfig, MetadataFieldConfig


class MetadataAndLinksTest(unittest.TestCase):
    def test_metadata_schema_service_validates_entity_fields(self) -> None:
        service = MetadataSchemaService(
            MetadataConfig(
                entities={
                    "notes": MetadataEntityConfig(
                        allow_extra=False,
                        fields={
                            "topic": MetadataFieldConfig(type="string"),
                            "priority": MetadataFieldConfig(type="integer"),
                        },
                    )
                }
            )
        )

        service.validate("notes", {"topic": "rag", "priority": 1})

        with self.assertRaises(ValueError):
            service.validate("notes", {"topic": "rag", "priority": "high"})

    def test_document_links_service_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "anchor.sqlite3"
            SqliteMigrationRepository(database_path=db_path).apply_pending()
            now = "2026-06-13T00:00:00+00:00"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO documents (
                        id, project, metatags, correlation_id, document_type, title, body, source, source_ref,
                        created_at, updated_at, deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        "01abc000-0000-7000-8000-000000000000",
                        "workspace",
                        "{}",
                        "01abc000-0000-7000-8000-000000000010",
                        "note",
                        "Source note",
                        "body",
                        "cli",
                        "",
                        now,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO documents (
                        id, project, metatags, correlation_id, document_type, title, body, source, source_ref,
                        created_at, updated_at, deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        "01abc000-0000-7000-8000-000000000001",
                        "workspace",
                        "{}",
                        "01abc000-0000-7000-8000-000000000011",
                        "note",
                        "Target note",
                        "body",
                        "cli",
                        "",
                        now,
                        now,
                    ),
                )
                connection.commit()
            service = DocumentLinksService(
                repository=SqliteLinksRepository(database_path=db_path),
                config=LinksConfig(relation_types=["references", "blocks"]),
            )

            created = service.create("01abc000-0000-7000-8000-000000000000", "01abc000-0000-7000-8000-000000000001", "references")
            listed = service.list_by_source(created.source_id)

            self.assertEqual(created.relation_type, "references")
            self.assertEqual(listed.count, 1)
            self.assertEqual(listed.links[0].target_id, created.target_id)
            self.assertTrue(service.delete(created.source_id, created.target_id, created.relation_type))
