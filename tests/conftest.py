import os
import sys
import tempfile

import pytest

# Configure the app for testing *before* main is imported.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_tmp, "test.db")
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["SECRET_KEY"] = "test-secret"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


def make_cafe(**overrides):
    data = dict(
        name="Cafe", map_url="https://maps.example/x", img_url="https://img.example/x.jpg",
        location="Soho", seats="20-30", coffee_price="£2.50",
        has_wifi=True, has_sockets=True, has_toilet=True, can_take_calls=True, lat=51.5, lng=-0.1,
    )
    data.update(overrides)
    return main.Cafe(**data)


@pytest.fixture
def client(monkeypatch):
    main.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    monkeypatch.setattr(main, "geocode", lambda query: (51.5, -0.1))
    monkeypatch.setattr(main, "UPLOAD_DIR", tempfile.mkdtemp())
    with main.app.app_context():
        main.db.drop_all()
        main.db.create_all()
        main.db.session.add_all([
            make_cafe(name="Alpha", location="Peckham", coffee_price="£3.00", seats="50+"),
            make_cafe(name="Beta", location="Soho", coffee_price="£2.00", seats="10-20", has_wifi=False),
            make_cafe(name="Gamma", location="Soho", coffee_price="£2.50", seats="20-30", has_sockets=False),
        ])
        main.db.session.commit()
    return main.app.test_client()


@pytest.fixture
def admin(client):
    client.post("/login", data={"password": "test-password"})
    return client
