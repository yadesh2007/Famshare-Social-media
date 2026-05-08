from functools import wraps
from flask import session, redirect, url_for, flash, request
from utils.helpers import current_user

def safe_next_path():
    """Keep users on this site after login and avoid external redirects."""
    next_path = request.full_path
    if next_path.endswith("?"):
        next_path = next_path[:-1]
    return next_path


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login", next=safe_next_path()))

        user = current_user()
        if user is None:
            session.clear()
            flash("Your session expired. Please login again.", "warning")
            return redirect(url_for("login", next=safe_next_path()))

        session["username"] = user["username"]
        return view(*args, **kwargs)
    return wrapped_view
