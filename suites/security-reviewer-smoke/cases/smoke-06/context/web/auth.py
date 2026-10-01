from flask import redirect, request

from .session import check_password, start_session


def login_done(user):
    start_session(user)
    return redirect(request.args.get("next", "/"))
