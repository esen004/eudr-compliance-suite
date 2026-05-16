"""WSGI config for EUDR Compliance Suite."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eudr_project.settings')

application = get_wsgi_application()
