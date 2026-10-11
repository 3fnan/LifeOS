# LifeGrid

LifeGrid is a Django web application that helps users turn long-term goals into manageable, scheduled work. Users create goals, break them down into roadmaps, milestones, checkpoints, and tasks, then assign tasks to time slots in a weekly calendar. The dashboard brings together today’s planned work, upcoming scheduled tasks, and completion progress.

## Distinctiveness and Complexity

LifeGrid is distinct from the earlier CS50 Web projects because it is a personal goal-planning and scheduling application, rather than a social network, auction site, e-commerce site, email client, or wiki. Its central purpose is to help one authenticated user move from an abstract goal to small, actionable tasks and then assign those tasks to time in a calendar. It is not based on the course’s Pizza project and does not reuse the core interaction model of the other projects.

The application’s complexity begins with its connected data model. A `Goal` belongs to a user and has one `Roadmap`. A roadmap contains multiple `Milestone` objects, each milestone contains multiple `Checkpoint` objects, and each checkpoint contains multiple `Task` objects. A task can have multiple `Schedule` records. This six-level structure is more involved than a flat to-do list: the application must create, edit, delete, retrieve, and display objects through several relationships while preserving their parent-child context. Goal and milestone progress are calculated from task completion below them.

LifeGrid also has planning rules and protection for user data. A goal validates that its target date is after its start date. Scheduling validates that an end time is later than its start time and prevents a user from creating overlapping schedule entries. Every view that reads or changes planning data filters through the authenticated user, so one user cannot access another user’s goals, tasks, or schedules merely by entering a different URL. The automated tests check that the task owner can toggle completion and that another authenticated user cannot toggle that task or delete the owner’s goal.

The project uses Django and JavaScript in complementary ways. Django provides the models, forms, authentication, server-side validation, database queries, templates, and CRUD views. On the goal-detail page, JavaScript uses the Fetch API to send a task-completion request asynchronously. When Django confirms the update, JavaScript changes the task display and recalculates goal and milestone progress without a full-page reload. The dashboard also derives today’s schedules, completion counts, scheduled minutes, completed minutes, and the five nearest upcoming schedules from database data.

The interface is responsive as well as functional. CSS media queries alter the sidebar, forms, task controls, schedule cards, and calendar at tablet and phone widths. The weekly calendar changes from seven columns to two columns and then one column, and controls stack where space is limited. The relational planning structure, scheduling validation, authorization, asynchronous updates, derived progress, and responsive interface together make LifeGrid substantially more complex than a basic task tracker.

## Features

- Account registration, login, and logout using Django's built-in authentication.
- Personal goal management with category, priority, status, available days per week, hours per day, start date, and target date.
- A one-to-one roadmap for each goal.
- Nested planning structure: **Goal → Roadmap → Milestone → Checkpoint → Task**.
- Create, edit, and delete goals, roadmaps, milestones, checkpoints, and tasks.
- Task statuses and a toggle to mark a task completed or return it to pending; completion timestamps are recorded.
- Schedule tasks with a date, start time, end time, status, and notes.
- Validation that a scheduled end time is later than its start time and that a user's schedules do not overlap.
- Dashboard showing the user's goals, today's scheduled work and completion progress, plus the next five upcoming schedules.
- Week-based calendar with previous/next-week navigation and schedule editing.
- Per-user access control: users can access and change only their own goals and associated planning data.

## Tech stack

- Python
- Django 6.1.1
- SQLite (development database)
- Django templates, CSS, and JavaScript

## Project structure

```text
lifegrid/             Django project configuration
core/                 Main application: models, forms, views, URLs, templates, and static files
core/migrations/      Database migrations
manage.py             Django management entry point
```

### Root files

- `manage.py`: Django’s command-line entry point for running the server, migrations, checks, and tests.
- `requirements.txt`: Lists the Python dependency or dependencies required to run the project.
- `.gitignore`: Excludes the virtual environment, local SQLite database, environment file, caches, IDE files, and generated static/media folders from Git.
- `README.md`: Documents the application and its setup.

### `lifegrid/`

- `settings.py`: Configures installed apps, the SQLite database, templates, static files, authentication redirects, and development settings.
- `urls.py`: Defines project-level routes for the Django admin, authentication, and the `core` application.
- `asgi.py` and `wsgi.py`: ASGI and WSGI deployment entry points.
- `__init__.py`: Marks the directory as a Python package.

### `core/` and its migrations

- `models.py`: Defines Goal, Roadmap, Milestone, Checkpoint, Task, and Schedule and their relationships.
- `forms.py`: Defines model forms and validation for planning objects, tasks, and schedules.
- `views.py`: Handles registration, dashboard data, CRUD operations, task toggling, scheduling, and the calendar.
- `urls.py`: Defines the application’s routes.
- `tests.py`: Tests task completion and authorization boundaries between users.
- `admin.py`: Registers all six application models with Django’s admin site.
- `apps.py` and `__init__.py`: Provide application and Python-package configuration.
- `migrations/0001_initial.py`: Creates the initial Goal and Roadmap models.
- `migrations/0002_milestone.py`: Adds the Milestone model.
- `migrations/0003_checkpoint_task.py`: Adds Checkpoint and Task models.
- `migrations/0004_schedule.py`: Adds the Schedule model.
- `migrations/0005_remove_goal_goal_type_goal_category_and_more.py`: Replaces the original goal type and adds category, priority, days per week, and hours per day fields.

### `core/templates/` and `core/static/`

- `templates/core/base.html`: Shared page layout, navigation, stylesheet, and JavaScript inclusion.
- `templates/core/dashboard.html`, `goal_detail.html`, and `calendar.html`: The dashboard, goal workspace, and weekly calendar pages.
- `templates/core/create_goal.html`, `edit_goal.html`, and `delete_goal.html`: Goal-management pages.
- `templates/core/create_roadmap.html`, `edit_roadmap.html`, and `delete_roadmap.html`: Roadmap-management pages.
- `templates/core/create_milestone.html`, `edit_milestone.html`, and `delete_milestone.html`: Milestone-management pages.
- `templates/core/create_checkpoint.html`, `edit_checkpoint.html`, and `delete_checkpoint.html`: Checkpoint-management pages.
- `templates/core/create_task.html`, `edit_task.html`, and `delete_task.html`: Task-management pages.
- `templates/core/schedule_task.html` and `edit_schedule.html`: Schedule creation and editing pages.
- `templates/core/registration/login.html` and `registration.html`: Login and registration pages.
- `static/core/css/style.css`: Application styling and responsive layouts.
- `static/core/js/app.js`: Asynchronous task completion and client-side progress updates.

## Local setup

These steps assume Python is installed and that commands are run from the cloned project directory.

```powershell
git clone -b web50/projects/2020/x/capstone https://github.com/me50/3fnan.git LifeOS
cd LifeOS
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

On macOS or Linux, activate the virtual environment with `source venv/bin/activate` instead.

The local secret key can be supplied through `DJANGO_SECRET_KEY`; if it is not supplied, the development settings use the repository's development fallback. Do not use the fallback with production settings.

## Database and running the app

Apply the included migrations, then start Django's development server:

```powershell
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`, register an account, and create a goal. Django's admin is available at `http://127.0.0.1:8000/admin/` after creating an administrator account with:

```powershell
python manage.py createsuperuser
```

## Tests

Run the automated test suite with:

```powershell
python manage.py test
```

The current tests cover task-completion behavior and user authorization: an owner can toggle a task, while another authenticated user cannot toggle that task or delete the owner's goal.

## Demo / submission notes

A useful demonstration flow is:

1. Register a new account and sign in.
2. Create a goal and its roadmap.
3. Add a milestone, checkpoint, and task.
4. Schedule the task, then show it in the calendar and dashboard.
5. Mark the task complete to show progress and completion status.
6. Sign in as a different user and show that the first user's goal URLs are not accessible.

The project currently uses local development settings: `DEBUG` is enabled, `ALLOWED_HOSTS` is empty, and SQLite is used as the development database. The repository includes a `requirements.txt` file with the Django dependency. Production deployment configuration and a hosted demo URL are not included.
