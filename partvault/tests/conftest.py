import pytest

from partvault.database.connection import init_db, get_session
from partvault.database.seed import seed_database


@pytest.fixture(scope="session", autouse=True)
def test_database(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("db") / "test.db")
    init_db(db_path)
    seed_database()
    return db_path


@pytest.fixture
def session():
    with get_session() as s:
        yield s
