"""ASGI config for EUDR Compliance Suite."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eudr_project.settings')

application = get_asgi_application()
