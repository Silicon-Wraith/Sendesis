import os

from flask import Flask, abort, request, send_file

app = Flask(__name__)
UPLOAD_DIR = "/srv/uploads"


@app.get("/download")
def download():
    name = request.args.get("name", "")
    if not name:
        abort(404)
    return send_file(os.path.join(UPLOAD_DIR, name))
