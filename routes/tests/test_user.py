import alembic.config
from unittest import IsolatedAsyncioTestCase

from fastapi.testclient import TestClient

from core.security import generate_hash_password, generate_token_from_user
from main import app
from models import db, engine, get_db_sync, get_db_sync_for_test
from models.User import MANAGEMENT_PARTICIPANT, User
from schemas.user import UserListResponse, UserQrDetail
from uuid import uuid4


class TestUser(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        alembic_args = ["upgrade", "head"]
        alembic.config.main(argv=alembic_args)
        self.connection = engine.connect()
        self.trans = self.connection.begin()
        self.db = db(bind=self.connection, join_transaction_mode="create_savepoint")

    async def test_get_user_by_id(self):
        # Given
        searched_user = User(
            id=str(uuid4()),
            username="searcheduser",
            email="searcheduser@local.com",
            password=generate_hash_password("password"),
            # participant_type=MANAGEMENT_PARTICIPANT,
            is_active=True,
        )
        self.db.add(searched_user)
        new_user = User(
            username="testuser",
            email="testuser@local.com",
            password=generate_hash_password("password"),
            # participant_type=MANAGEMENT_PARTICIPANT,
            is_active=True,
        )
        self.db.add(new_user)
        self.db.commit()
        app.dependency_overrides[get_db_sync] = get_db_sync_for_test(db=self.db)
        client = TestClient(app)
        response = client.post(
            "/auth/email/signin/",
            json={"email": "testuser@local.com", "password": "password"},
        )
        token = response.json().get("token", None)

        # When 1
        response = client.get(f"/user/{searched_user.id}")
        # Expect 1
        # asser public profile checked
        self.assertEqual(response.status_code, 401)

        # When 2
        response = client.get(
            f"/user/{searched_user.id}", headers={"Authorization": f"Bearer {token}"}
        )
        # Expect 2
        self.assertEqual(response.status_code, 200)
        self.assertIn("experience", response.json())
        self.assertIn("industry_categories", response.json())
        self.assertIn("gender", response.json())
        self.assertIn("city", response.json())
        self.assertIn("zip_code", response.json())
        self.assertIn("address", response.json())
        self.assertIn("date_of_birth", response.json())
        self.assertIn("t_shirt_size", response.json())
        self.assertIn("email", response.json())
        self.assertIn("phone", response.json())
        self.assertIn("github_username", response.json())
        self.assertIn("linkedin_username", response.json())
        self.assertIn("twitter_username", response.json())
        self.assertIn("facebook_username", response.json())
        self.assertNotIn("is_active", response.json())
        self.assertNotIn("created_at", response.json())
        self.assertNotIn("updated_at", response.json())
        self.assertIn("interest", response.json())
        self.assertIn("profile_picture", response.json())
        self.assertIn("first_name", response.json())
        self.assertIn("last_name", response.json())
        self.assertIn("job_category", response.json())
        self.assertIn("job_title", response.json())
        self.assertIn("country", response.json())
        self.assertIn("bio", response.json())
        self.assertIn("participant_type", response.json())
        self.assertIn("coc_acknowledged", response.json())
        self.assertIn("terms_agreed", response.json())
        self.assertIn("privacy_agreed", response.json())
        self.assertIn("share_my_email_and_phone_number", response.json())
        self.assertIn("share_my_job_and_company", response.json())
        self.assertIn("share_my_location", response.json())
        self.assertIn("share_my_interest", response.json())
        self.assertIn("share_my_public_social_media", response.json())
        self.assertIn("share_my_data_to_sponsor", response.json())
        self.assertIn("retain_my_data_for_next_pycon", response.json())

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
                count=14,
                page_size=10,
                page=1,
                page_count=2,
                results=[
                    UserQrDetail(
                        id=str(user.id),
                        username=user.username,
                        first_name=user.first_name,
                        last_name=user.last_name,
                        email=user.email,
                    )
                    for user in expected_users
                ],
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
                count=1,
                page_size=10,
                page=1,
                page_count=1,
                results=[
                    UserQrDetail(
                        id=str(users[11].id),
                        username=users[11].username,
                        first_name=users[11].first_name,
                        last_name=users[11].last_name,
                        email=users[11].email,
                    )
                ],
            ).model_dump(),
        )

    async def test_get_detail_user_for_qr(self):
        # Given
        management_user = User(
            id="123e4567-e89b-12d3-a456-426614174000",
            username="admin",
            participant_type=MANAGEMENT_PARTICIPANT,
            email="admin@local.com",
        )
        non_management_user = User(
            id="223e4567-e89b-12d3-a456-426614174000",
            username="member-non-management",
            participant_type="Speaker",
            email="member@local.com",
        )
        target_user = User(
            id="323e4567-e89b-12d3-a456-426614174000",
            username="target-member",
            first_name="Target",
            last_name="Member",
            email="target@local.com",
        )

        self.db.add(management_user)
        self.db.add(non_management_user)
        self.db.add(target_user)
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
        response = client.get(f"/user/{target_user.id}/qr/")

        # Expect 1
        self.assertEqual(response.status_code, 401)
        self.assertDictEqual(response.json(), {"message": "Unauthorized"})

        # When 2 - non management user
        response = client.get(
            f"/user/{target_user.id}/qr/",
            headers={"Authorization": f"Bearer {non_management_token}"},
        )

        # Expect 2
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), "Forbidden: Insufficient permissions")

        # When 3 - management user with invalid user id
        response = client.get(
            "/user/423e4567-e89b-12d3-a456-426614174000/qr/",
            headers={"Authorization": f"Bearer {management_token}"},
        )

        # Expect 3
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(response.json(), {"message": "User not found"})

        # When 4 - management user with valid user id
        response = client.get(
            f"/user/{target_user.id}/qr/",
            headers={"Authorization": f"Bearer {management_token}"},
        )

        # Expect 4
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            UserQrDetail(
                id=str(target_user.id),
                username=target_user.username,
                first_name=target_user.first_name,
                last_name=target_user.last_name,
                email=target_user.email,
            ).model_dump(),
        )

    def tearDown(self):
        self.db.close()
        self.trans.rollback()
        self.connection.close()
        app.dependency_overrides.pop(get_db_sync, None)
