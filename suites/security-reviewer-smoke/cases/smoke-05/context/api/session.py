import base64
import pickle

from flask import request


def restore_session() -> dict:
    """Read the client's saved UI state from the ui_state cookie."""
    raw = request.cookies.get("ui_state")
    if not raw:
        return {}
    state = pickle.loads(base64.b64decode(raw))
    return state if isinstance(state, dict) else {}
