from .models import Goal


def sidebar(request):
    """The signed-in user's active goals, for the sidebar on every page."""
    if not request.user.is_authenticated:
        return {}
    goals = Goal.objects.filter(user=request.user, status="active").order_by("target_date", "id")
    return {"sidebar_goals": goals.only("id", "title")}
