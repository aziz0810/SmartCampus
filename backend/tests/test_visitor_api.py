import os
import unittest
from collections.abc import Iterator
from unittest.mock import patch

os.environ.setdefault("APP_DB_NAME", "test_db")
os.environ.setdefault("APP_DB_USER", "test_user")
os.environ.setdefault("APP_DB_PASSWORD", "test_password")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db
from app.main import app
from app.models.base import Base
from app.models.visitor import VisitorMessage, VisitorSession


class VisitorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[VisitorSession.__table__, VisitorMessage.__table__],
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.db = self.session_factory()

        def override_get_db() -> Iterator[Session]:
            yield self.db

        app.dependency_overrides[get_db] = override_get_db
        self.cleanup_patcher = patch(
            "app.lifespan.purge_expired_visitor_sessions"
        )
        self.cleanup_patcher.start()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        self.cleanup_patcher.stop()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_liveness_probe_does_not_need_the_database(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_missing_token_is_rejected(self) -> None:
        session_id = self.client.post("/api/visitor-sessions").json()["session_id"]
        response = self.client.get(f"/api/visitor-sessions/{session_id}/messages")
        self.assertEqual(response.status_code, 401)

    def test_visitor_session_endpoints_require_token_and_support_lifecycle(self) -> None:
        created = self.client.post("/api/visitor-sessions")
        self.assertEqual(created.status_code, 201)
        session = created.json()
        session_id = session["session_id"]
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        blank = self.client.post(
            f"/api/visitor-sessions/{session_id}/messages",
            headers=headers,
            json={"content": "   "},
        )
        self.assertEqual(blank.status_code, 422)

        added = self.client.post(
            f"/api/visitor-sessions/{session_id}/messages",
            headers=headers,
            json={"content": "Bonjour"},
        )
        self.assertEqual(added.status_code, 201)
        self.assertEqual(added.json()["messages_remaining"], session["message_limit"] - 1)

        messages = self.client.get(
            f"/api/visitor-sessions/{session_id}/messages",
            headers=headers,
        )
        self.assertEqual(messages.status_code, 200)
        self.assertEqual(messages.json()[0]["content"], "Bonjour")

        unauthorized = self.client.get(
            f"/api/visitor-sessions/{session_id}/messages",
            headers={"Authorization": "Bearer invalid"},
        )
        self.assertEqual(unauthorized.status_code, 401)

        deleted = self.client.delete(
            f"/api/visitor-sessions/{session_id}",
            headers=headers,
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(
            self.client.get(
                f"/api/visitor-sessions/{session_id}/messages",
                headers=headers,
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
