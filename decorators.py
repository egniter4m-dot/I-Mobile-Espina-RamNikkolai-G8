from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def role_required(*roles):
    """
    Anonymous users -> /login/. Logged-in users with the wrong role are sent back
    to their own dashboard with an error message (blocks horizontal/vertical escalation, BR-09).
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                messages.error(request, "You don't have permission to open that page.")
                return redirect(request.user.dashboard_url_name)
            return view_func(request, *args, **kwargs)

        return login_required(_wrapped)

    return decorator


member_required = role_required("MEMBER")
admin_required = role_required("ADMIN")
