import alembic.config
from unittest import IsolatedAsyncioTestCase

from fastapi.testclient import TestClient

from core.security import generate_token_from_user
from main import app
from models import db, engine, get_db_sync, get_db_sync_for_test
from models.User import MANAGEMENT_PARTICIPANT, User
from schemas.user import UserListResponse


class TestUser(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        alembic_args = ["upgrade", "head"]
        alembic.config.main(argv=alembic_args)
        self.connection = engine.connect()
        self.trans = self.connection.begin()
        self.db = db(bind=self.connection, join_transaction_mode="create_savepoint")

    async def test_get_user_for_qr(self):
        # Given
        management_user = User(
            id="123e4567-e89b-12d3-a456-426614174000",
            username="admin",
            participant_type=MANAGEMENT_PARTICIPANT,
            email="zzadmin@local.com",
        )
        non_management_user = User(
            id="223e4567-e89b-12d3-a456-426614174000",
            username="member-non-management",
            participant_type="Speaker",
            email="zzz-member@local.com",
        )
        self.db.add(management_user)
        self.db.add(non_management_user)

        users = []
        for i in range(12):
            user = User(
                id=f"00000000-0000-0000-0000-0000000000{i + 10:02}",
                username=f"member{i}",
                first_name="Member",
                last_name=f"{i}",
                email=f"member{i:02}@local.com",
            )
            users.append(user)
            self.db.add(user)

        self.db.commit()

        (management_token, _) = await generate_token_from_user(
            db=self.db, user=management_user
        )
        (non_management_token, _) = await generate_token_from_user(
            db=self.db, user=non_management_user
        )

        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)

        # When 1 - request without token
        response = client.get("/user/qr/")

        # Expect 1
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(response.json(), {"message": "Unauthorized"})

        # When 2 - non management user
        response = client.get(
            "/user/qr/",
            headers={"Authorization": f"Bearer {non_management_token}"},
        )

        # Expect 2
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), "Forbidden: Insufficient permissions")

        # When 3 - management user without search
        response = client.get(
            "/user/qr/",
            headers={"Authorization": f"Bearer {management_token}"},
        )

        # Expect 3 - limited to 10 users because all=False
        self.assertEqual(response.status_code, 200)
        expected_users = sorted(users, key=lambda u: u.email)[:10]
        self.assertDictEqual(
            response.json(),
            UserListResponse(
                results=[
                    UserListResponse.UserQrDetail(
                        id=str(user.id),
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        email=user.email,
                    )
                    for user in expected_users
                ]
            ).model_dump(),
        )

        # When 4 - management user with search
        response = client.get(
            "/user/qr/",
            headers={"Authorization": f"Bearer {management_token}"},
            params={"search": "member11"},
        )

        # Expect 4
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            UserListResponse(
                results=[
                    UserListResponse.UserQrDetail(
                        id=str(users[11].id),
                        username=users[11].username,
                        first_name=users[11].first_name,
                        last_name=users[11].last_name,
                        email=users[11].email,
                    )
                ]
            ).model_dump(),
        )

    def tearDown(self):
        self.db.close()
        self.trans.rollback()
        self.connection.close()
        app.dependency_overrides.pop(get_db_sync, None)
