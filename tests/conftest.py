import os

import pytest
from flask import Flask

from api import api_bp
from config import MOBILE_API_TOKEN


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(api_bp, url_prefix="/api")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {MOBILE_API_TOKEN}"}
