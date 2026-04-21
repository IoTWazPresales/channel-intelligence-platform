"""Stable logger name for DEV-ONLY Celery/thread dispatch warnings (local development)."""

import logging

DEV_CELERY_LOGGER = logging.getLogger("cip.dev_celery")
