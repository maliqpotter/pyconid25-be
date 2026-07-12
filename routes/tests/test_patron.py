import os
import uuid
from unittest import IsolatedAsyncioTestCase

import alembic.config
from fastapi.testclient import TestClient
from sqlalchemy import select

from core.security import generate_token_from_user
from main import app
from models import db, engine, get_db_sync, get_db_sync_for_test
from models.Patron import Patron
from models.User import MANAGEMENT_PARTICIPANT, User
from settings import FILE_STORAGE_PATH


class TestPatron(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        alembic_args = ["upgrade", "head"]
        alembic.config.main(argv=alembic_args)

    def setUp(self):
        self.connection = engine.connect()
        self.trans = self.connection.begin()
        self.session = db(
            bind=self.connection, join_transaction_mode="create_savepoint"
        )

        self.active_patron_id = uuid.uuid4()
        self.image_patron_id = uuid.uuid4()
        self.image_path = "patron/test-patron.png"
        os.makedirs(
            os.path.dirname(f"{FILE_STORAGE_PATH}/{self.image_path}"), exist_ok=True
        )
        with open(f"{FILE_STORAGE_PATH}/{self.image_path}", "wb") as file:
            file.write(b"test-image")

        self.silver_patron_id = uuid.uuid4()
        self.session.add(
            Patron(
                id=self.active_patron_id,
                name="Python Supporter",
                tier="gold",
            )
        )
        self.session.add(
            Patron(
                id=self.image_patron_id,
                name="Image Patron",
                tier="ultimate",
                image=self.image_path,
            )
        )
        self.session.add(
            Patron(
                id=self.silver_patron_id,
                name="Silver Patron",
                tier="silver",
            )
        )
        self.user = User(
            username="admin",
            participant_type=MANAGEMENT_PARTICIPANT,
        )
        self.session.add(self.user)
        self.session.commit()

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.session)
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        if os.path.exists(f"{FILE_STORAGE_PATH}/{self.image_path}"):
            os.remove(f"{FILE_STORAGE_PATH}/{self.image_path}")
        self.session.close()
        self.trans.rollback()
        self.connection.close()

    async def get_management_token(self):
        token, _ = await generate_token_from_user(db=self.session, user=self.user)
        return token

    async def test_list_patrons_is_public_without_pagination(self):
        response = self.client.get("/patron/")

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "page" not in data
        assert "page_size" not in data
        assert "count" not in data
        assert "page_count" not in data
        assert len(data["results"]) == 3
        assert [patron["tier"] for patron in data["results"]] == [
            "ultimate",
            "gold",
            "silver",
        ]
        assert all("has_image" in patron for patron in data["results"])
        assert (
            next(
                patron
                for patron in data["results"]
                if patron["id"] == str(self.image_patron_id)
            )["has_image"]
            is True
        )
        assert (
            next(
                patron
                for patron in data["results"]
                if patron["id"] == str(self.active_patron_id)
            )["has_image"]
            is False
        )

    async def test_create_patron_requires_management_user(self):
        response = self.client.post(
            "/patron/",
            data={"name": "New Patron", "tier": "gold"},
        )

        assert response.status_code == 401

    async def test_create_patron(self):
        token = await self.get_management_token()
        response = self.client.post(
            "/patron/",
            headers={"Authorization": f"Bearer {token}"},
            data={"name": "New Patron", "tier": "platinum"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Patron"
        assert data["tier"] == "platinum"
        assert "id" in data

    async def test_create_patron_with_invalid_tier(self):
        token = await self.get_management_token()
        response = self.client.post(
            "/patron/",
            headers={"Authorization": f"Bearer {token}"},
            data={"name": "Invalid Patron", "tier": "bronze"},
        )

        assert response.status_code == 422

    async def test_get_patron_detail(self):
        token = await self.get_management_token()
        response = self.client.get(
            f"/patron/{self.active_patron_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "id": str(self.active_patron_id),
            "name": "Python Supporter",
            "tier": "gold",
        }

    async def test_get_patron_detail_not_found(self):
        token = await self.get_management_token()
        random_id = uuid.uuid4()
        response = self.client.get(
            f"/patron/{random_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["message"] == f"patron with id = {random_id} not found"

    async def test_update_patron_without_image_keeps_existing_image(self):
        token = await self.get_management_token()
        response = self.client.put(
            f"/patron/{self.image_patron_id}",
            headers={"Authorization": f"Bearer {token}"},
            data={"name": "Updated Patron", "tier": "silver"},
        )

        assert response.status_code == 200
        assert response.json() == {
            "id": str(self.image_patron_id),
            "name": "Updated Patron",
            "tier": "silver",
        }
        patron = self.session.execute(
            select(Patron).where(Patron.id == self.image_patron_id)
        ).scalar()
        assert patron.image == self.image_path

    async def test_delete_patron(self):
        token = await self.get_management_token()
        response = self.client.delete(
            f"/patron/{self.active_patron_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204
        patron = self.session.execute(
            select(Patron).where(Patron.id == self.active_patron_id)
        ).scalar()
        assert patron is None

    async def test_delete_patron_removes_image_file(self):
        token = await self.get_management_token()
        image_full_path = f"{FILE_STORAGE_PATH}/{self.image_path}"
        assert os.path.exists(image_full_path)

        response = self.client.delete(
            f"/patron/{self.image_patron_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204
        patron = self.session.execute(
            select(Patron).where(Patron.id == self.image_patron_id)
        ).scalar()
        assert patron is None
        assert not os.path.exists(image_full_path)

    async def test_get_patron_image_is_public(self):
        response = self.client.get(f"/patron/{self.image_patron_id}/image/")

        assert response.status_code == 200
        assert response.content == b"test-image"

    async def test_get_patron_image_not_found(self):
        response = self.client.get(f"/patron/{self.active_patron_id}/image/")

        assert response.status_code == 404
        assert response.json()["message"] == "Patron image not found"
