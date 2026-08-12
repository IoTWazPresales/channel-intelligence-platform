"""BACKLOG-026: Product Master generic pipeline path is retired."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.ingestion.pipeline import _process_product_master, process_import_job_sync


def test_process_product_master_handler_raises() -> None:
    with pytest.raises(ValueError, match="BACKLOG-026"):
        _process_product_master(MagicMock(), MagicMock(), MagicMock(), {})


def test_process_import_job_sync_refuses_product_master() -> None:
    db = MagicMock()
    job = MagicMock()
    job.template_slug = "product_master"
    job.file_headers = None
    db.scalar.return_value = job

    with pytest.raises(ValueError, match="Import Centre Product Master workflow"):
        process_import_job_sync(db, 1)
