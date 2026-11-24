"""ASGI entry point: uvicorn ragdesk.main:app"""

import logging

from ragdesk.api.app import create_app
from ragdesk.bootstrap import build_container
from ragdesk.config import Settings

settings = Settings()
logging.basicConfig(
    level=settings.log_level, format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
)
app = create_app(lambda: build_container(settings))
