
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import Goal, Roadmap, Milestone, Checkpoint, Task


class ToggleTaskSecurityTests(TestCase): #authorization
    def setUp(self):
        User = get_user_model()

        self.owner = User.objects.create_user(
            username="owner",
            password="test-password-123",
        )

        self.other_user = User.objects.create_user(
            username="other",
            password="test-password-123",
        )

        # Create a goal belonging to the owner.
        goal = Goal.objects.create(
            user=self.owner,
            title="Learn Django",
            category="education",
            priority="high",
            days_per_week=5,
            hours_per_day=1,
            start_date="2026-10-10",
            target_date="2026-12-10",
        )

        roadmap = Roadmap.objects.create(
            goal=goal,
            title="Django Roadmap",
        )

        milestone = Milestone.objects.create(
            roadmap=roadmap,
            title="Learn the fundamentals",
            order=1,
        )

        checkpoint = Checkpoint.objects.create(
            milestone=milestone,
            title="Build my first app",
            order=1,
        )

        self.task = Task.objects.create(
            checkpoint=checkpoint,
            title="Learn Django testing",
            status="pending",
        )
    

    def test_owner_can_toggle_task(self):
        self.client.force_login(self.owner)

        url = reverse("toggle_task", args=[self.task.id])
        response = self.client.post(url)

        self.task.refresh_from_db()

        self.assertEqual(self.task.status, "completed")
        self.assertIsNotNone(self.task.completed_at)


    def test_other_user_cannot_toggle_task(self): #fynctionality
        self.client.force_login(self.other_user)

        url = reverse("toggle_task", args=[self.task.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "pending")

    
    def test_other_user_cannot_delete_goal(self): #authorization
        self.client.force_login(self.other_user)

        url = reverse("delete_goal", args=[self.task.checkpoint.milestone.roadmap.goal.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            Goal.objects.filter(
                id=self.task.checkpoint.milestone.roadmap.goal.id,
                user=self.owner,
            ).exists()
        )

    
    def test_owner_can_undo_completed_task(self):
        self.task.status = "completed"
        self.task.completed_at = "2026-10-10T10:00:00Z"
        self.task.save()

        self.client.force_login(self.owner)
        url = reverse("toggle_task", args=[self.task.id])
        response = self.client.post(url)

        self.task.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.task.status, "pending")
        self.assertIsNone(self.task.completed_at)

    def test_anonymous_user_cannot_toggle_task(self):
        url = reverse("toggle_task", args=[self.task.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "pending")

    def test_get_request_cannot_delete_goal(self):
        self.client.force_login(self.owner)
        goal_id = self.task.checkpoint.milestone.roadmap.goal.id

        url = reverse("delete_goal", args=[goal_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Goal.objects.filter(id=goal_id, user=self.owner).exists()
        )


