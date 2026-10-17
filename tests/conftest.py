from pathlib import Path
import pytest
from app.seed import seed_database
from app.tools.database import ReadOnlySQL

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def data_dir():
    return ROOT / 'data'


@pytest.fixture
def db_path(tmp_path, data_dir):
    path = tmp_path / 'store.sqlite3'
    seed_database(data_dir, path)
    return path


@pytest.fixture
def database(db_path):
    return ReadOnlySQL(db_path)
