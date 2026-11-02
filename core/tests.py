import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from core.forms import GoalForm, TimeBlockForm
from core.models import Goal, Phase, Step, Task, TimeBlock
from core import ai_draft, stats
from core.scheduler import plan_goal

PASSWORD = "test-password-123"


# ---------------------------------------------------------------------------
# Shared isolated fixtures. Every test runs on Django's throwaway test DB.
# ---------------------------------------------------------------------------
def make_tree(user, title="Learn Django", hours_per_day=1, days_per_week=5):
    """Create a full Goal > Phase > Step > Task > TimeBlock chain."""
    goal = Goal.objects.create(
        user=user, title=title, category="education", priority="high",
        days_per_week=days_per_week, hours_per_day=hours_per_day,
        start_date="2026-10-10", target_date="2026-12-10",
    )
    phase = Phase.objects.create(goal=goal, title="Phase", order=1)
    step = Step.objects.create(phase=phase, title="Step", order=1)
    task = Task.objects.create(step=step, title="Task")
    block = TimeBlock.objects.create(
        task=task, date="2026-11-02", start_time="09:00", end_time="10:00",
    )
    return {"goal": goal, "phase": phase, "step": step, "task": task, "block": block}


def object_routes(tree):
    """Every URL that reads or changes one user-owned object."""
    return [
        ("goal_detail", tree["goal"].id), ("edit_goal", tree["goal"].id),
        ("auto_schedule", tree["goal"].id), ("draft_plan", tree["goal"].id),
        ("delete_goal", tree["goal"].id), ("create_phase", tree["goal"].id),
        ("edit_phase", tree["phase"].id), ("delete_phase", tree["phase"].id),
        ("create_step", tree["phase"].id),
        ("edit_step", tree["step"].id), ("delete_step", tree["step"].id),
        ("create_task", tree["step"].id),
        ("edit_task", tree["task"].id), ("delete_task", tree["task"].id),
        ("schedule_task", tree["task"].id), ("toggle_task", tree["task"].id),
        ("edit_block", tree["block"].id), ("delete_block", tree["block"].id),
    ]


POST_ONLY = ("toggle_task", "delete_block")
BLOCK_DATA = {"status": "planned"}


class OwnedTreeTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner", password=PASSWORD)
        self.other = User.objects.create_user(username="other", password=PASSWORD)
        self.tree = make_tree(self.owner)
        self.client.force_login(self.owner)

    def counts(self):
        return [m.objects.count() for m in (Goal, Phase, Step, Task, TimeBlock)]


# ---------------------------------------------------------------------------
# Task completion (original suite, on the new structure)
# ---------------------------------------------------------------------------
class ToggleTaskTests(OwnedTreeTestCase):
    def toggle(self, client=None):
        return (client or self.client).post(reverse("toggle_task", args=[self.tree["task"].id]))

    def test_owner_can_toggle_and_undo_task(self):
        task = self.tree["task"]
        self.toggle()
        task.refresh_from_db()
        self.assertEqual(task.status, Task.DONE)
        self.assertIsNotNone(task.completed_at)

        response = self.toggle()
        task.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.status, Task.TODO)
        self.assertIsNone(task.completed_at)

    def test_other_user_cannot_toggle_task(self):
        other = Client()
        other.force_login(self.other)
        self.assertEqual(self.toggle(other).status_code, 404)
        self.tree["task"].refresh_from_db()
        self.assertEqual(self.tree["task"].status, Task.TODO)

    def test_anonymous_user_cannot_toggle_task(self):
        self.assertEqual(self.toggle(Client()).status_code, 302)
        self.tree["task"].refresh_from_db()
        self.assertEqual(self.tree["task"].status, Task.TODO)

    def test_toggle_returns_json_for_fetch(self):
        response = self.client.post(
            reverse("toggle_task", args=[self.tree["task"].id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.json(), {"success": True, "status": "done"})


# ---------------------------------------------------------------------------
# Authorization boundaries
# ---------------------------------------------------------------------------
class CrossUserIsolationTests(OwnedTreeTestCase):
    def test_other_user_gets_404_on_every_object_route_and_nothing_changes(self):
        before = self.counts()
        other = Client()
        other.force_login(self.other)

        for name, obj_id in object_routes(self.tree):
            url = reverse(name, args=[obj_id])
            with self.subTest(route=name, method="POST"):
                self.assertEqual(other.post(url, {"title": "hijack"}).status_code, 404)
            if name not in POST_ONLY:
                with self.subTest(route=name, method="GET"):
                    self.assertEqual(other.get(url).status_code, 404)

        self.assertEqual(self.counts(), before)
        self.tree["task"].refresh_from_db()
        self.assertEqual(self.tree["task"].status, Task.TODO)
        self.assertEqual(Goal.objects.get().title, "Learn Django")

    def test_dashboard_and_calendar_only_show_own_data(self):
        make_tree(self.other, title="Other users secret goal")
        Task.objects.filter(step__phase__goal__user=self.other).update(title="Other users secret task")
        for url in (reverse("dashboard"), reverse("goal_list"), reverse("calendar") + "?week=2026-11-02"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "secret")

    def test_other_users_blocks_do_not_cause_overlap(self):
        other_tree = make_tree(self.other)
        other_tree["block"].delete()
        form = TimeBlockForm(
            dict(BLOCK_DATA, date="2026-11-02", start_time="09:00", end_time="10:00"),
            task=other_tree["task"],
        )
        self.assertTrue(form.is_valid(), form.errors)


class AnonymousAccessTests(OwnedTreeTestCase):
    def test_every_page_redirects_anonymous_users_to_login(self):
        anon = Client()
        routes = [(name, [obj_id]) for name, obj_id in object_routes(self.tree)]
        routes += [("dashboard", []), ("calendar", []), ("create_goal", []), ("goal_list", [])]
        for name, args in routes:
            url = reverse(name, args=args)
            with self.subTest(route=name):
                response = anon.post(url) if name in POST_ONLY else anon.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("login")))
        self.assertEqual(TimeBlock.objects.count(), 1)


class HttpMethodTests(OwnedTreeTestCase):
    def test_state_changing_endpoints_reject_get(self):
        for name, obj_id in [("toggle_task", self.tree["task"].id), ("delete_block", self.tree["block"].id)]:
            with self.subTest(route=name):
                self.assertEqual(self.client.get(reverse(name, args=[obj_id])).status_code, 405)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(TimeBlock.objects.count(), 1)

    def test_get_on_delete_pages_only_confirms(self):
        before = self.counts()
        for level in ("goal", "phase", "step", "task"):
            with self.subTest(level=level):
                response = self.client.get(reverse(f"delete_{level}", args=[self.tree[level].id]))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "core/base.html")
        self.assertEqual(self.counts(), before)

    def test_csrf_is_enforced_on_toggle(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        response = strict.post(reverse("toggle_task", args=[self.tree["task"].id]))
        self.assertEqual(response.status_code, 403)
        self.tree["task"].refresh_from_db()
        self.assertEqual(self.tree["task"].status, Task.TODO)


class RedirectAndEscapingTests(OwnedTreeTestCase):
    def test_login_ignores_external_next(self):
        response = Client().post(
            reverse("login") + "?next=https://evil.example/",
            {"username": "owner", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

    def test_toggle_from_parameter_only_allows_known_pages(self):
        url = reverse("toggle_task", args=[self.tree["task"].id])
        self.assertEqual(self.client.post(url + "?from=dashboard")["Location"], reverse("dashboard"))
        self.assertEqual(self.client.post(url + "?from=calendar")["Location"], reverse("calendar"))
        self.assertEqual(
            self.client.post(url + "?from=https://evil.example/")["Location"],
            reverse("goal_detail", args=[self.tree["goal"].id]),
        )

    def test_user_content_is_escaped_everywhere(self):
        payload = '<script>alert("x")</script>'
        for key in ("goal", "phase", "step", "task"):
            obj = self.tree[key]
            obj.title = payload
            obj.description = payload
            obj.save()
        for url in (reverse("goal_detail", args=[self.tree["goal"].id]), reverse("dashboard"),
                    reverse("calendar") + "?week=2026-11-02",
                    reverse("schedule_task", args=[self.tree["task"].id])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, payload)


# ---------------------------------------------------------------------------
# Time blocks: validation, overlap, capacity warnings
# ---------------------------------------------------------------------------
class TimeBlockValidationTests(OwnedTreeTestCase):
    def post_block(self, **data):
        return self.client.post(reverse("schedule_task", args=[self.tree["task"].id]), dict(BLOCK_DATA, **data))

    def test_missing_date_or_time_is_a_form_error_not_a_crash(self):
        cases = {
            "no date": {"start_time": "11:00", "end_time": "12:00"},
            "no start": {"date": "2026-11-03", "end_time": "12:00"},
            "no end": {"date": "2026-11-03", "start_time": "11:00"},
            "bad time": {"date": "2026-11-03", "start_time": "nope", "end_time": "12:00"},
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                response = self.post_block(**data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertEqual(TimeBlock.objects.count(), 1)

    def test_end_must_be_after_start(self):
        response = self.post_block(date="2026-11-03", start_time="12:00", end_time="12:00")
        self.assertContains(response, "End time must be later than start time.")
        self.assertEqual(TimeBlock.objects.count(), 1)

    def test_overlap_is_rejected_and_names_the_conflict(self):
        response = self.post_block(date="2026-11-02", start_time="09:30", end_time="10:00")
        self.assertContains(response, "overlaps with")
        self.assertContains(response, "09:00–10:00")
        self.assertEqual(TimeBlock.objects.count(), 1)

    def test_touching_blocks_are_not_overlaps(self):
        # 10:00-10:30 starts exactly when the 09:00-10:00 block ends. (It also
        # exceeds the 1h/day plan, so it needs the capacity confirmation.)
        response = self.post_block(date="2026-11-02", start_time="10:00", end_time="10:30",
                                   confirm_over_capacity="on")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimeBlock.objects.count(), 2)

    def test_can_overlap_blocks_do_not_conflict(self):
        confirm = {"confirm_over_capacity": "on"}
        response = self.post_block(date="2026-11-02", start_time="09:30", end_time="10:00",
                                   allow_overlap="on", **confirm)
        self.assertEqual(response.status_code, 302)
        # An existing "can overlap" block does not block a normal one either.
        block = TimeBlock.objects.exclude(pk=self.tree["block"].pk).get()
        self.assertTrue(block.allow_overlap)
        self.tree["block"].delete()
        form = TimeBlockForm(dict(BLOCK_DATA, date="2026-11-02", start_time="09:00",
                                  end_time="09:45", **confirm), task=self.tree["task"])
        self.assertTrue(form.is_valid(), form.errors)

    def test_skipped_blocks_free_their_slot(self):
        self.tree["block"].status = TimeBlock.SKIPPED
        self.tree["block"].save()
        response = self.post_block(date="2026-11-02", start_time="09:00", end_time="10:00")
        self.assertEqual(response.status_code, 302)

    def test_editing_a_block_does_not_conflict_with_itself(self):
        block = self.tree["block"]
        response = self.client.post(reverse("edit_block", args=[block.id]),
                                    dict(BLOCK_DATA, date="2026-11-02", start_time="09:15", end_time="10:00"))
        self.assertEqual(response.status_code, 302)
        block.refresh_from_db()
        self.assertEqual(block.start_time, datetime.time(9, 15))

    def test_failed_edit_leaves_block_unchanged(self):
        block = self.tree["block"]
        response = self.client.post(reverse("edit_block", args=[block.id]),
                                    dict(BLOCK_DATA, date="", start_time="11:00", end_time="10:00"))
        self.assertEqual(response.status_code, 200)
        block.refresh_from_db()
        self.assertEqual(block.start_time, datetime.time(9, 0))


class CapacityWarningTests(OwnedTreeTestCase):
    """Goal plan: 1 hour/day, 5 days/week. One 1h block exists on Mon 2026-11-02."""

    def post_block(self, **data):
        return self.client.post(reverse("schedule_task", args=[self.tree["task"].id]), dict(BLOCK_DATA, **data))

    def test_within_plan_saves_without_warning(self):
        response = self.post_block(date="2026-11-03", start_time="09:00", end_time="10:00")
        self.assertEqual(response.status_code, 302)

    def test_over_daily_hours_warns_then_saves_when_confirmed(self):
        response = self.post_block(date="2026-11-02", start_time="18:00", end_time="18:30")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1h 30m of “Learn Django” on Mon Nov 02")
        self.assertContains(response, "Schedule anyway")
        self.assertEqual(TimeBlock.objects.count(), 1)

        response = self.post_block(date="2026-11-02", start_time="18:00", end_time="18:30",
                                   confirm_over_capacity="on")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimeBlock.objects.count(), 2)

    def test_over_days_per_week_warns(self):
        for day in (3, 4, 5, 6):  # Tue-Fri -> 5 days used
            TimeBlock.objects.create(task=self.tree["task"], date=f"2026-11-0{day}",
                                     start_time="09:00", end_time="09:30")
        response = self.post_block(date="2026-11-07", start_time="09:00", end_time="09:30")
        self.assertContains(response, "6 days of “Learn Django” in the week of Nov 02")
        # A different week is fine.
        response = self.post_block(date="2026-11-09", start_time="09:00", end_time="09:30")
        self.assertEqual(response.status_code, 302)

    def test_no_schedule_anyway_toggle_when_within_plan(self):
        response = self.client.get(reverse("schedule_task", args=[self.tree["task"].id]))
        self.assertNotContains(response, "Schedule anyway")


class MissedStatusTests(OwnedTreeTestCase):
    def setUp(self):
        super().setUp()
        self.tree["block"].refresh_from_db()  # load real date/time objects

    def test_planned_block_in_the_past_shows_as_missed_until_task_is_done(self):
        block = self.tree["block"]  # 2026-11-02 09:00-10:00
        later = timezone.make_aware(datetime.datetime(2026, 11, 2, 12, 0))
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertEqual(block.effective_status, TimeBlock.MISSED)
            self.tree["task"].status = Task.DONE
            self.tree["task"].save()
            block.refresh_from_db()
            self.assertEqual(block.effective_status, TimeBlock.PLANNED)

    def test_future_block_is_planned(self):
        earlier = timezone.make_aware(datetime.datetime(2026, 11, 2, 8, 0))
        with mock.patch("django.utils.timezone.now", return_value=earlier):
            self.assertEqual(self.tree["block"].effective_status, TimeBlock.PLANNED)


class DerivedStatusTests(OwnedTreeTestCase):
    def test_phase_and_step_status_follow_tasks(self):
        phase, step, task = self.tree["phase"], self.tree["step"], self.tree["task"]
        self.assertEqual((phase.status, step.status), ("not_started", "not_started"))
        task.status = Task.DOING
        task.save()
        self.assertEqual((phase.status, step.status), ("in_progress", "in_progress"))
        Task.objects.create(step=step, title="Second", status=Task.DONE)
        task.status = Task.DONE
        task.save()
        self.assertEqual((phase.status, step.status), ("done", "done"))
        self.assertEqual(phase.progress, 100)


# ---------------------------------------------------------------------------
# Goals, calendar and pages
# ---------------------------------------------------------------------------
class GoalFormValidationTests(TestCase):
    base = {"title": "Run a 10k", "category": "health", "priority": "medium",
            "days_per_week": 3, "hours_per_day": 1, "status": "active"}

    def test_missing_dates_are_field_errors_not_a_crash(self):
        for missing in ("start_date", "target_date"):
            data = dict(self.base, start_date="2026-11-01", target_date="2026-12-01")
            data.pop(missing)
            with self.subTest(missing=missing):
                form = GoalForm(data)
                self.assertFalse(form.is_valid())
                self.assertIn(missing, form.errors)

    def test_target_before_start_is_reported_on_target_date(self):
        form = GoalForm(dict(self.base, start_date="2026-12-01", target_date="2026-11-01"))
        self.assertFalse(form.is_valid())
        self.assertIn("target_date", form.errors)

    def test_failed_create_saves_nothing_and_shows_each_error_once(self):
        user = get_user_model().objects.create_user(username="u", password=PASSWORD)
        self.client.force_login(user)
        response = self.client.post(reverse("create_goal"),
                                    dict(self.base, start_date="2026-12-01", target_date="2026-11-01"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Goal.objects.count(), 0)
        self.assertContains(response, "Target date must be after the start date.", count=1)

    def test_out_of_range_values_are_rejected(self):
        for field, value in (("days_per_week", 8), ("days_per_week", 0),
                             ("hours_per_day", 25), ("hours_per_day", 0)):
            with self.subTest(field=field, value=value):
                form = GoalForm(dict(self.base, start_date="2026-11-01",
                                     target_date="2026-12-01", **{field: value}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)


class CalendarWeekTests(OwnedTreeTestCase):
    def get_week(self, value):
        return self.client.get(reverse("calendar") + f"?week={value}")

    def test_any_date_snaps_to_monday_through_sunday(self):
        response = self.get_week("2026-11-04")  # a Wednesday
        self.assertEqual(response.context["start_date"], datetime.date(2026, 11, 2))
        self.assertEqual(response.context["end_date"], datetime.date(2026, 11, 8))
        self.assertEqual(response.context["previous_week"], datetime.date(2026, 10, 26))
        self.assertEqual(response.context["next_week"], datetime.date(2026, 11, 9))
        self.assertEqual(response.context["week_minutes"], 60)
        self.assertContains(response, "Task")

    def test_extreme_or_invalid_weeks_fall_back_to_current_week(self):
        current = self.client.get(reverse("calendar")).context["start_date"]
        self.assertEqual(current.weekday(), 0)
        for value in ("9999-12-31", "0001-01-01", "garbage", "2026-02-30"):
            with self.subTest(week=value):
                response = self.get_week(value)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["start_date"], current)


class PageTests(OwnedTreeTestCase):
    def test_edit_form_status_keeps_completed_at_in_sync(self):
        task = self.tree["task"]
        url = reverse("edit_task", args=[task.id])
        data = {"title": "Task", "description": "", "estimated_minutes": 30}
        self.client.post(url, dict(data, status="done"))
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)
        self.client.post(url, dict(data, status="doing"))
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)

    def test_add_phase_is_available_when_phases_exist(self):
        response = self.client.get(reverse("goal_detail", args=[self.tree["goal"].id]))
        self.assertContains(response, reverse("create_phase", args=[self.tree["goal"].id]))

    def test_descriptions_are_multiline(self):
        for name, obj in (("create_phase", "goal"), ("create_step", "phase"), ("create_task", "step")):
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=[self.tree[obj].id]))
                self.assertContains(response, '<textarea name="description"')

    def test_success_message_after_create(self):
        response = self.client.post(reverse("create_phase", args=[self.tree["goal"].id]),
                                    {"title": "Build", "description": "", "order": 2}, follow=True)
        self.assertContains(response, "Phase added.")

    def test_add_and_schedule_goes_straight_to_scheduling(self):
        response = self.client.post(reverse("create_task", args=[self.tree["step"].id]),
                                    {"title": "New", "description": "", "estimated_minutes": 30,
                                     "status": "todo", "then": "schedule"})
        task = Task.objects.get(title="New")
        self.assertRedirects(response, reverse("schedule_task", args=[task.id]))

    def test_goal_page_queries_do_not_grow_with_tasks(self):
        url = reverse("goal_detail", args=[self.tree["goal"].id])
        # session, user, goal, phases, steps, tasks, blocks, sidebar goals
        with self.assertNumQueries(8):
            self.client.get(url)
        for i in range(5):
            Task.objects.create(step=self.tree["step"], title=f"Extra {i}")
        Phase.objects.create(goal=self.tree["goal"], title="Another phase", order=2)
        with self.assertNumQueries(8):
            self.client.get(url)


class CascadeTests(OwnedTreeTestCase):
    def test_each_level_deletes_everything_below_it(self):
        # Remaining [Goal, Phase, Step, Task, TimeBlock] counts.
        expected_after = {
            "task": [1, 1, 1, 0, 0], "step": [1, 1, 0, 0, 0],
            "phase": [1, 0, 0, 0, 0], "goal": [0, 0, 0, 0, 0],
        }
        for level, expected in expected_after.items():
            with self.subTest(level=level):
                Goal.objects.all().delete()
                tree = make_tree(self.owner)
                response = self.client.post(reverse(f"delete_{level}", args=[tree[level].id]))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.counts(), expected)

    def test_removing_a_block_keeps_the_task(self):
        response = self.client.post(reverse("delete_block", args=[self.tree["block"].id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.counts(), [1, 1, 1, 1, 0])


class GoalListAndFormattingTests(OwnedTreeTestCase):
    def test_goal_list_shows_own_goals_with_progress(self):
        self.tree["task"].status = Task.DONE
        self.tree["task"].save()
        make_tree(self.other, title="Not mine")
        response = self.client.get(reverse("goal_list"))
        self.assertContains(response, "Learn Django")
        self.assertNotContains(response, "Not mine")
        self.assertContains(response, "1/1")
        self.assertContains(response, 'aria-label="100% of tasks done"')

    def test_goal_list_empty_state_teaches_next_step(self):
        Goal.objects.all().delete()
        response = self.client.get(reverse("goal_list"))
        self.assertContains(response, "Set your first goal")

    def test_duration_filter(self):
        from core.templatetags.planner import duration
        self.assertEqual([duration(m) for m in (0, 45, 60, 105, "x")], ["0m", "45m", "1h", "1h 45m", ""])

    def test_pages_have_no_banned_decoration(self):
        # Guard the design direction: no heading kickers, gradient text or progress rings.
        urls = [reverse("dashboard"), reverse("goal_list"), reverse("calendar"),
                reverse("goal_detail", args=[self.tree["goal"].id]),
                reverse("schedule_task", args=[self.tree["task"].id])]
        for url in urls:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                for banned in ('class="eyebrow"', "gradient-text", 'class="ring'):
                    self.assertNotIn(banned, html)


# ---------------------------------------------------------------------------
# Complete user journeys
# ---------------------------------------------------------------------------
class UserJourneyTests(TestCase):
    def test_register_plan_schedule_and_complete(self):
        c = Client()
        response = c.post(reverse("register"), {
            "username": "newuser", "password1": "a-Strong-pass-981", "password2": "a-Strong-pass-981"})
        self.assertRedirects(response, reverse("login"))
        response = c.post(reverse("login"), {"username": "newuser", "password": "a-Strong-pass-981"})
        self.assertRedirects(response, reverse("dashboard"))
        self.assertContains(c.get(reverse("dashboard")), "set a goal yet.")

        response = c.post(reverse("create_goal"), {
            "title": "Ship LifeGrid", "description": "Launch it publicly", "category": "projects",
            "priority": "high", "days_per_week": 5, "hours_per_day": 2,
            "start_date": "2026-11-01", "target_date": "2026-12-31", "status": "active"})
        goal = Goal.objects.get(title="Ship LifeGrid")
        self.assertRedirects(response, reverse("goal_detail", args=[goal.id]))
        self.assertEqual(goal.user.username, "newuser")

        for i in (1, 2):
            c.post(reverse("create_phase", args=[goal.id]), {"title": f"Phase {i}", "description": "", "order": i})
        self.assertEqual(goal.phases.count(), 2)
        phase = goal.phases.get(order=1)
        c.post(reverse("create_step", args=[phase.id]), {"title": "Fix bugs", "description": "", "order": 1})
        step = phase.steps.get()
        c.post(reverse("create_task", args=[step.id]),
               {"title": "Write tests", "description": "", "estimated_minutes": 60, "status": "todo"})
        task = step.tasks.get()

        response = c.post(reverse("schedule_task", args=[task.id]), dict(
            BLOCK_DATA, date="2026-11-04", start_time="18:00", end_time="19:00"))
        self.assertRedirects(response, reverse("goal_detail", args=[goal.id]))
        self.assertContains(c.get(reverse("calendar") + "?week=2026-11-04"), "Write tests")

        c.post(reverse("toggle_task", args=[task.id]))
        detail = c.get(reverse("goal_detail", args=[goal.id]))
        self.assertEqual(detail.context["progress"], 100)

        self.assertRedirects(c.post(reverse("logout")), reverse("login"))
        self.assertEqual(c.get(reverse("dashboard")).status_code, 302)

    def test_registration_rejects_weak_or_mismatched_passwords(self):
        for p1, p2 in (("short", "short"), ("a-Strong-pass-981", "different-pass-981"),
                       ("12345678", "12345678")):
            with self.subTest(p1=p1):
                response = self.client.post(reverse("register"), {"username": "x", "password1": p1, "password2": p2})
                self.assertEqual(response.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(username="x").exists())

    def test_wrong_password_does_not_log_in(self):
        get_user_model().objects.create_user(username="u", password=PASSWORD)
        response = self.client.post(reverse("login"), {"username": "u", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


# ---------------------------------------------------------------------------
# The restructure migration keeps existing data
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Automatic scheduling
# ---------------------------------------------------------------------------
# Monday 2 Nov 2026, 08:00 — before the fixture's 09:00 block that day.
FIXED_NOW = timezone.make_aware(datetime.datetime(2026, 11, 2, 8, 0))


class AutoScheduleTests(OwnedTreeTestCase):
    def add_task(self, title, minutes, step=None):
        return Task.objects.create(step=step or self.tree["step"], title=title, estimated_minutes=minutes)

    def plan(self, goal=None, start="2026-11-02", window=("18:00", "21:00"), now=FIXED_NOW):
        return plan_goal(
            Goal.objects.get(pk=(goal or self.tree["goal"]).pk),
            start_date=datetime.date.fromisoformat(start),
            window_start=datetime.time.fromisoformat(window[0]),
            window_end=datetime.time.fromisoformat(window[1]),
            now=now,
        )

    @staticmethod
    def summary(plan):
        return [(b.task.title, str(b.date), f"{b.start_time:%H:%M}", f"{b.end_time:%H:%M}") for b in plan.blocks]

    def test_keeps_order_and_daily_budget_without_splitting_short_tasks(self):
        self.add_task("A", 45)
        self.add_task("B", 45)
        plan = self.plan()
        # Monday is already full (the fixture's 60-minute block); the original
        # task is scheduled, so only A and B are planned. B doesn't fit in
        # Tuesday's last 15 minutes, so it moves whole to Wednesday.
        self.assertEqual(self.summary(plan), [
            ("A", "2026-11-03", "18:00", "18:45"),
            ("B", "2026-11-04", "18:00", "18:45"),
        ])
        self.assertEqual(plan.unplaced, [])
        self.assertEqual(TimeBlock.objects.count(), 1)  # nothing saved

    def test_splits_tasks_longer_than_a_day_into_daily_pieces(self):
        self.add_task("Long", 150)
        self.assertEqual(self.summary(self.plan()), [
            ("Long", "2026-11-03", "18:00", "19:00"),
            ("Long", "2026-11-04", "18:00", "19:00"),
            ("Long", "2026-11-05", "18:00", "18:30"),
        ])

    def test_whole_task_waits_for_a_gap_big_enough(self):
        other_goal = make_tree(self.owner, title="Other goal")
        TimeBlock.objects.filter(task=other_goal["task"]).update(date="2026-11-03", start_time="18:20", end_time="19:00")
        self.add_task("A", 45)
        self.assertEqual(self.summary(self.plan()), [("A", "2026-11-03", "19:00", "19:45")])

    def test_respects_days_per_week(self):
        goal = self.tree["goal"]
        goal.days_per_week = 2
        goal.save()
        for title in "ABC":
            self.add_task(title, 60)
        # Monday already counts as one of this week's two days.
        self.assertEqual([d for _, d, _, _ in self.summary(self.plan())],
                         ["2026-11-03", "2026-11-09", "2026-11-10"])

    def test_works_around_other_blocks(self):
        other_goal = make_tree(self.owner, title="Other goal")
        TimeBlock.objects.filter(task=other_goal["task"]).update(date="2026-11-03", start_time="18:00", end_time="18:30")
        overlap_ok = TimeBlock.objects.create(task=other_goal["task"], date="2026-11-03",
                                              start_time="18:30", end_time="21:00", allow_overlap=True)
        self.add_task("A", 60)
        self.assertEqual(self.summary(self.plan()), [("A", "2026-11-03", "18:30", "19:30")])
        overlap_ok.delete()

    def test_reschedules_missed_and_skips_done_tasks(self):
        self.tree["block"].date = "2026-10-30"  # in the past, still planned -> missed
        self.tree["block"].save()
        Task.objects.create(step=self.tree["step"], title="Done already", status=Task.DONE)
        titles = [t for t, *_ in self.summary(self.plan())]
        self.assertEqual(titles, ["Task"])

    def test_reports_tasks_that_do_not_fit_before_target_date(self):
        goal = self.tree["goal"]
        goal.target_date = datetime.date(2026, 11, 3)
        goal.save()
        self.add_task("A", 60)
        self.add_task("B", 60)
        plan = self.plan()
        self.assertEqual([t for t, *_ in self.summary(plan)], ["A"])
        self.assertEqual([t.title for t in plan.unplaced], ["B"])

    def test_nothing_is_placed_in_the_past_today(self):
        self.tree["block"].delete()
        self.add_task("A", 30)
        now = timezone.make_aware(datetime.datetime(2026, 11, 2, 19, 2))
        plan = self.plan(now=now)
        self.assertEqual(self.summary(plan)[0], ("Task", "2026-11-02", "19:05", "19:35"))

    @mock.patch("django.utils.timezone.now", return_value=FIXED_NOW)
    def test_preview_then_save(self, _now):
        self.add_task("A", 45)
        url = reverse("auto_schedule", args=[self.tree["goal"].id])
        data = {"start_date": "2026-11-02", "window_start": "18:00", "window_end": "21:00"}

        self.assertContains(self.client.get(url), "Plan my weeks")
        preview = self.client.post(url, data)
        self.assertContains(preview, "Add 1 block to calendar")
        self.assertEqual(TimeBlock.objects.count(), 1)

        response = self.client.post(url, dict(data, then="save"))
        self.assertRedirects(response, reverse("goal_detail", args=[self.tree["goal"].id]))
        block = TimeBlock.objects.get(task__title="A")
        self.assertEqual((str(block.date), f"{block.start_time:%H:%M}"), ("2026-11-03", "18:00"))

    @mock.patch("django.utils.timezone.now", return_value=FIXED_NOW)
    def test_form_rejects_bad_window_and_dates(self, _now):
        url = reverse("auto_schedule", args=[self.tree["goal"].id])
        cases = [
            ({"start_date": "2026-11-02", "window_start": "21:00", "window_end": "18:00"}, "latest finish must be later"),
            ({"start_date": "2026-11-01", "window_start": "18:00", "window_end": "21:00"}, "today or a later date"),
            ({"start_date": "2027-01-01", "window_start": "18:00", "window_end": "21:00"}, "target date is 10 Dec 2026"),
        ]
        for data, message in cases:
            with self.subTest(message=message):
                self.assertContains(self.client.post(url, dict(data, then="save")), message)
        self.assertEqual(TimeBlock.objects.count(), 1)


class DraftPlanTests(OwnedTreeTestCase):
    PHASES = [{"title": "Basics", "steps": [
        {"title": "Models", "tasks": [{"title": "Read the docs", "minutes": 45}, {"title": "Build one", "minutes": 60}]},
    ]}]

    def url(self):
        return reverse("draft_plan", args=[self.tree["goal"].id])

    def test_outline_round_trip(self):
        phases, errors = ai_draft.parse_outline(ai_draft.to_outline(self.PHASES))
        self.assertEqual(errors, [])
        self.assertEqual(phases, self.PHASES)

    def test_outline_defaults_minutes_and_reports_bad_lines(self):
        phases, errors = ai_draft.parse_outline("# P\n## S\n- No time given\n")
        self.assertEqual(phases[0]["steps"][0]["tasks"], [{"title": "No time given", "minutes": 30}])
        _, errors = ai_draft.parse_outline("- orphan task\njust text\n")
        self.assertEqual(len(errors), 2)
        self.assertIn("Line 1", errors[0])

    @mock.patch("core.ai_draft.draft_plan", return_value=PHASES)
    def test_draft_shows_editable_outline_and_saves_nothing(self, draft):
        before = self.counts()
        response = self.client.post(self.url(), {"level": "beginner"})
        self.assertContains(response, "## Models")
        self.assertContains(response, "- Read the docs (45 min)")
        self.assertEqual(self.counts(), before)
        draft.assert_called_once()

    def test_save_appends_edited_outline_after_existing_phases(self):
        outline = "# Basics\n## Models\n- Read the docs (45 min)\n- Build one (1 hour typo)\n"
        response = self.client.post(self.url(), {"level": "beginner", "outline": outline, "then": "save"})
        self.assertEqual(response.status_code, 302)
        phase = Phase.objects.get(title="Basics")
        self.assertEqual(phase.goal, self.tree["goal"])
        self.assertEqual(phase.order, 2)
        tasks = Task.objects.filter(step__phase=phase).order_by("id")
        self.assertEqual([(t.title, t.estimated_minutes) for t in tasks],
                         [("Read the docs", 45), ("Build one (1 hour typo)", 30)])

    def test_invalid_outline_is_not_saved(self):
        before = self.counts()
        response = self.client.post(self.url(), {"level": "beginner", "outline": "- orphan\n", "then": "save"})
        self.assertContains(response, "Fix the draft")
        self.assertEqual(self.counts(), before)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_missing_key_shows_error_with_manual_fallback(self):
        response = self.client.post(self.url(), {"level": "beginner"})
        self.assertContains(response, "AI drafting isn&#x27;t available right now.")
        self.assertNotContains(response, "Gemini")
        self.assertContains(response, reverse("create_phase", args=[self.tree["goal"].id]))

    @mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"})
    def test_busy_model_falls_back_to_next_and_sends_only_goal_info(self):
        import io, json, urllib.error
        body = {"candidates": [{"content": {"parts": [{"text": json.dumps({"phases": self.PHASES})}]}}]}
        busy = urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"{}"))
        ok = mock.MagicMock()
        ok.__enter__.return_value = io.BytesIO(json.dumps(body).encode())
        with mock.patch("urllib.request.urlopen", side_effect=[busy, ok]) as urlopen:
            phases = ai_draft.draft_plan(Goal.objects.get(pk=self.tree["goal"].pk), "some")
        self.assertEqual(phases, self.PHASES)
        first, second = (call.args[0] for call in urlopen.call_args_list)
        self.assertIn(ai_draft.MODELS[0], first.full_url)
        self.assertIn(ai_draft.MODELS[1], second.full_url)
        prompt = json.loads(second.data)["contents"][0]["parts"][0]["text"]
        self.assertIn("Learn Django", prompt)
        self.assertNotIn(self.owner.username, prompt)


class DashboardStatsTests(OwnedTreeTestCase):
    TODAY = datetime.date(2026, 11, 4)  # a Wednesday

    def block(self, date, status="planned", start="09:00", end="10:00", task=None):
        return TimeBlock.objects.create(task=task or self.tree["task"], date=date,
                                        start_time=start, end_time=end, status=status)

    def setUp(self):
        super().setUp()
        self.tree["block"].delete()

    def test_streak_counts_done_days_and_skips_rest_days(self):
        self.block("2026-11-04", "planned")   # today, not done yet: doesn't break
        self.block("2026-11-03", "done")
        # 2026-11-02 has nothing planned: a rest day
        self.block("2026-11-01", "done")
        self.block("2026-10-31", "skipped")    # breaks the streak
        self.block("2026-10-30", "done")
        self.assertEqual(stats.streak(self.owner, self.TODAY), 2)

    def test_streak_includes_today_once_done(self):
        self.block("2026-11-04", "done")
        self.block("2026-11-03", "done")
        self.assertEqual(stats.streak(self.owner, self.TODAY), 2)

    def test_week_hours_count_only_done_blocks_this_week(self):
        self.block("2026-11-02", "done", "09:00", "10:30")
        self.block("2026-11-03", "planned")
        self.block("2026-10-30", "done")  # last week
        week = stats.week_hours(self.owner, self.TODAY)
        self.assertEqual(week["done"], 90)
        self.assertEqual(week["budget"], 60 * 5)

    def test_goal_at_risk_when_work_exceeds_time_left(self):
        goal = self.tree["goal"]  # 1h a day, 5 days a week, target 2026-12-10
        self.assertEqual(stats.goals_at_risk(self.owner, self.TODAY), [])
        Task.objects.create(step=self.tree["step"], title="Huge", estimated_minutes=60 * 60)
        [risk] = stats.goals_at_risk(self.owner, self.TODAY)
        self.assertEqual(risk["goal"], goal)
        self.assertGreater(risk["short"], 0)

    @mock.patch("django.utils.timezone.now",
                return_value=timezone.make_aware(datetime.datetime(2026, 11, 4, 12, 0)))
    def test_skipped_and_missed_this_week(self, _now):
        skipped = self.block("2026-11-02", "skipped")
        missed = self.block("2026-11-03", "planned")
        self.block("2026-11-03", "done", "11:00", "12:00")
        self.block("2026-10-30", "skipped")  # last week
        self.assertEqual(stats.skipped_and_missed(self.owner, self.TODAY), [skipped, missed])

    def test_ticking_a_task_marks_its_past_blocks_done_and_unticking_reverts(self):
        today = timezone.localdate()
        past = self.block(today)
        future = self.block(today + datetime.timedelta(days=3))
        url = reverse("toggle_task", args=[self.tree["task"].id])
        self.client.post(url)
        past.refresh_from_db(); future.refresh_from_db()
        self.assertEqual((past.status, future.status), ("done", "planned"))
        self.client.post(url)
        past.refresh_from_db()
        self.assertEqual(past.status, "planned")

    def test_dashboard_shows_stats(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Streak")
        self.assertContains(response, "This week")
        self.assertContains(response, "At risk")
        self.assertContains(response, "Skipped or missed")


class RestructureMigrationTests(TransactionTestCase):
    before = [("core", "0005_remove_goal_goal_type_goal_category_and_more")]
    after = [("core", "0008_new_statuses_and_overlap")]

    def test_old_data_is_converted_without_loss(self):
        # Safety guard: this test migrates the schema back and forth, so it must
        # only ever run against the throwaway test database, never a real one.
        db_name = str(connection.settings_dict["NAME"])
        if not (connection.is_in_memory_db() or "test" in db_name.lower()):
            self.fail(f"Refusing to run migration test against non-test database {db_name!r}")

        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps

        user = old.get_model("auth", "User").objects.create(username="legacy")
        goal = old.get_model("core", "Goal").objects.create(
            user=user, title="Old goal", days_per_week=3, hours_per_day=1,
            start_date="2026-10-01", target_date="2026-12-01")
        bare_goal = old.get_model("core", "Goal").objects.create(
            user=user, title="Goal without roadmap", days_per_week=2, hours_per_day=1,
            start_date="2026-10-01", target_date="2026-12-01")
        roadmap = old.get_model("core", "Roadmap").objects.create(
            goal=goal, title="Old roadmap", description="Roadmap notes")
        milestone = old.get_model("core", "Milestone").objects.create(
            roadmap=roadmap, title="Old milestone", order=2, status="completed")
        checkpoint = old.get_model("core", "Checkpoint").objects.create(
            milestone=milestone, title="Old checkpoint", order=1)
        Task = old.get_model("core", "Task")
        tasks = {s: Task.objects.create(checkpoint=checkpoint, title=f"T-{s}", status=s)
                 for s in ("pending", "in_progress", "completed")}
        Schedule = old.get_model("core", "Schedule")
        schedules = {s: Schedule.objects.create(task=tasks["pending"], date="2026-11-02",
                                                start_time=f"0{i}:00", end_time=f"0{i}:30", status=s)
                     for i, s in enumerate(("scheduled", "completed", "skipped"), start=1)}

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps

        NewGoal = new.get_model("core", "Goal")
        self.assertEqual(NewGoal.objects.get(pk=goal.pk).description, "Roadmap notes")
        self.assertEqual(NewGoal.objects.get(pk=bare_goal.pk).description, "")

        phase = new.get_model("core", "Phase").objects.get(pk=milestone.pk)
        self.assertEqual((phase.title, phase.order, phase.goal_id), ("Old milestone", 2, goal.pk))
        step = new.get_model("core", "Step").objects.get(pk=checkpoint.pk)
        self.assertEqual((step.title, step.phase_id), ("Old checkpoint", phase.pk))

        NewTask = new.get_model("core", "Task")
        self.assertEqual(
            {old_s: NewTask.objects.get(pk=t.pk).status for old_s, t in tasks.items()},
            {"pending": "todo", "in_progress": "doing", "completed": "done"},
        )
        self.assertTrue(all(NewTask.objects.get(pk=t.pk).step_id == step.pk for t in tasks.values()))

        Block = new.get_model("core", "TimeBlock")
        self.assertEqual(
            {old_s: Block.objects.get(pk=s.pk).status for old_s, s in schedules.items()},
            {"scheduled": "planned", "completed": "done", "skipped": "skipped"},
        )
        self.assertEqual(Block.objects.filter(allow_overlap=False).count(), 3)
