import os

# Tests default to the local SQLite fallback regardless of the production
# DATABASE_URL in environtment.env — set this before any import below can
# trigger config.py's load_dotenv(), which does not override an env var
# that's already present (even as ""). Set TEST_DATABASE_URL in the real
# shell environment to opt a run into exercising the Postgres path instead.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

import pytest
from flask import Flask

from api import api_bp
from config import MOBILE_API_TOKEN
from features.budget import budget_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(budget_bp, url_prefix="/api/budget")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {MOBILE_API_TOKEN}"}
