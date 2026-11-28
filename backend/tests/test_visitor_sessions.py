import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

os.environ.setdefault("APP_DB_NAME", "test_db")
os.environ.setdefault("APP_DB_USER", "test_user")
os.environ.setdefault("APP_DB_PASSWORD", "test_password")

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.visitor import VisitorMessage, VisitorSession
from app.services.visitor_sessions import (
    InvalidVisitorToken,
    VisitorMessageLimitReached,
    VisitorSessionExpired,
    VisitorSessionNotFound,
    add_assistant_message,
    add_user_message,
    create_visitor_session,
    get_recent_messages,
)


class VisitorSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            self.engine,
            tables=[VisitorSession.__table__, VisitorMessage.__table__],
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_tokens_are_unique_and_not_stored_in_plain_text(self) -> None:
        with self.session_factory() as db:
            session, token = create_visitor_session(db)
            another_session, another_token = create_visitor_session(db)

            self.assertNotEqual(token, another_token)
            self.assertNotEqual(session.token_hash, token)
            self.assertEqual(len(session.token_hash), 64)
            self.assertIsInstance(session.id, UUID)
            self.assertNotEqual(session.id, another_session.id)

    def test_memory_is_trimmed_and_session_message_cap_is_enforced(self) -> None:
        with (
            patch("app.services.visitor_sessions.settings.visitor_memory_max_messages", 1),
            patch("app.services.visitor_sessions.settings.visitor_session_max_messages", 2),
            self.session_factory() as db,
        ):
            session, token = create_visitor_session(db)
            add_user_message(db, session.id, token, "Premier")
            add_user_message(db, session.id, token, "Deuxième")

            recent = get_recent_messages(db, session.id, token)
            self.assertEqual([message.content for message in recent], ["Deuxième"])
            with self.assertRaises(VisitorMessageLimitReached):
                add_user_message(db, session.id, token, "Troisième")

    def test_expired_session_is_removed_and_cannot_be_read(self) -> None:
        with self.session_factory() as db:
            session, token = create_visitor_session(db)
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            session_id = session.id

            with self.assertRaises(VisitorSessionExpired):
                get_recent_messages(db, session_id, token)
            self.assertIsNone(db.get(VisitorSession, session_id))

    def test_wrong_token_is_rejected(self) -> None:
        with self.session_factory() as db:
            session, _ = create_visitor_session(db)

            with self.assertRaises(InvalidVisitorToken):
                get_recent_messages(db, session.id, "wrong-token")

    def test_wrong_token_cannot_delete_an_expired_session(self) -> None:
        with self.session_factory() as db:
            session, _ = create_visitor_session(db)
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

            with self.assertRaises(InvalidVisitorToken):
                get_recent_messages(db, session.id, "wrong-token")
            self.assertIsNotNone(db.get(VisitorSession, session.id))

    def test_assistant_replies_are_remembered_without_using_the_visitor_quota(
        self,
    ) -> None:
        with (
            patch("app.services.visitor_sessions.settings.visitor_memory_max_messages", 2),
            self.session_factory() as db,
        ):
            session, token = create_visitor_session(db)
            add_user_message(db, session.id, token, "Question 1")
            add_assistant_message(db, session.id, "Réponse 1")
            _, remaining = add_user_message(db, session.id, token, "Question 2")

            recent = get_recent_messages(db, session.id, token)
            self.assertEqual(
                [(m.role, m.content) for m in recent],
                [("assistant", "Réponse 1"), ("user", "Question 2")],
            )
            self.assertEqual(session.turn_count, 2)
            self.assertGreater(remaining, 0)

    def test_assistant_reply_requires_a_live_session(self) -> None:
        with self.session_factory() as db:
            with self.assertRaises(VisitorSessionNotFound):
                add_assistant_message(
                    db, UUID("00000000-0000-0000-0000-000000000000"), "x"
                )
            session, _ = create_visitor_session(db)
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
            with self.assertRaises(VisitorSessionExpired):
                add_assistant_message(db, session.id, "x")


if __name__ == "__main__":
    unittest.main()
