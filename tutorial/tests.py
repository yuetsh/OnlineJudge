from django.test import TestCase, Client
from django.contrib.auth import get_user_model
import json

from tutorial.models import Tutorial, Exercise

User = get_user_model()


def _json(response):
    return json.loads(response.content)


class ExerciseAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create(
            username="admin_test", admin_type="Super Admin", is_staff=True
        )
        self.admin.set_password("password")
        self.admin.save()

        self.tutorial = Tutorial.objects.create(
            title="Test Tutorial",
            content="Hello [[exercise:1]]",
            type="python",
            is_public=True,
            order=0,
            created_by=self.admin,
        )
        self.exercise = Exercise.objects.create(
            tutorial=self.tutorial,
            type="mcq",
            data={
                "question": "Which is valid?",
                "options": ["A", "B"],
                "answer": 1,
            },
            order=0,
        )

    def test_get_exercises_for_tutorial(self):
        resp = self.client.get(f"/api/exercises?tutorial_id={self.tutorial.id}")
        self.assertEqual(resp.status_code, 200)
        data = _json(resp)["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "mcq")

    def test_get_exercises_missing_tutorial_id(self):
        resp = self.client.get("/api/exercises")
        self.assertEqual(_json(resp)["error"], "error")

    def test_get_exercises_nonexistent_tutorial(self):
        resp = self.client.get("/api/exercises?tutorial_id=99999")
        self.assertEqual(_json(resp)["error"], "error")


class ExerciseAdminAPITest(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create(
            username="admin2_test", admin_type="Super Admin", is_staff=True
        )
        self.admin.set_password("password")
        self.admin.save()
        self.client.login(username="admin2_test", password="password")

        self.tutorial = Tutorial.objects.create(
            title="T",
            content="",
            type="python",
            is_public=False,
            order=0,
            created_by=self.admin,
        )

    def test_create_mcq(self):
        resp = self.client.post(
            "/api/admin/exercise",
            data=json.dumps({
                "tutorial_id": self.tutorial.id,
                "type": "mcq",
                "data": {"question": "Q?", "options": ["A", "B"], "answer": 0},
                "order": 0,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(_json(resp)["error"])
        self.assertEqual(Exercise.objects.count(), 1)

    def test_create_invalid_type(self):
        resp = self.client.post(
            "/api/admin/exercise",
            data=json.dumps({
                "tutorial_id": self.tutorial.id,
                "type": "bad_type",
                "data": {},
                "order": 0,
            }),
            content_type="application/json",
        )
        self.assertEqual(_json(resp)["error"], "error")

    def test_edit_exercise(self):
        ex = Exercise.objects.create(
            tutorial=self.tutorial,
            type="mcq",
            data={"question": "Old", "options": ["A", "B"], "answer": 0},
            order=0,
        )
        resp = self.client.put(
            "/api/admin/exercise",
            data=json.dumps({
                "id": ex.id,
                "type": "mcq",
                "data": {"question": "New", "options": ["A", "B"], "answer": 1},
                "order": 0,
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        ex.refresh_from_db()
        self.assertEqual(ex.data["question"], "New")

    def test_delete_exercise(self):
        ex = Exercise.objects.create(
            tutorial=self.tutorial,
            type="sort",
            data={"question": "Q", "lines": ["a", "b"]},
            order=0,
        )
        resp = self.client.delete(f"/api/admin/exercise?id={ex.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Exercise.objects.count(), 0)

    def test_requires_admin(self):
        self.client.logout()
        resp = self.client.post(
            "/api/admin/exercise",
            data=json.dumps({"tutorial_id": 1, "type": "mcq", "data": {}, "order": 0}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
