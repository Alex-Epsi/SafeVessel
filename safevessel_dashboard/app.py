"""
SafeVessel — Dashboard web
Sert la console de bord (page web) et son API, a heberger sur le Raspberry Pi.

Lancement :
  python app.py                          -> lit le vrai port serie (Arduino branche)
  SAFEVESSEL_SIMULATE=1 python app.py     -> mode simulation, sans materiel

Acces depuis un navigateur (PC ou telephone sur le meme reseau) :
  http://<ip_du_raspberry>:5000
"""
import os
import threading

from flask import Flask, render_template, jsonify, request, Response

from state import state
from db import init_db, fetch_events, clear_events, export_csv
from serial_reader import run_serial_loop
from simulate import run_simulation_loop

SIMULATE = os.environ.get("SAFEVESSEL_SIMULATE", "0") == "1"
SERIAL_PORT = os.environ.get("SAFEVESSEL_PORT", "/dev/ttyACM0")
SERIAL_BAUD = int(os.environ.get("SAFEVESSEL_BAUD", "9600"))
HTTP_PORT = int(os.environ.get("SAFEVESSEL_HTTP_PORT", "5000"))

app = Flask(__name__)
_stop_event = threading.Event()
_started = False


@app.route("/")
def dashboard():
    return render_template("dashboard.html", simulate=SIMULATE, port=SERIAL_PORT)


@app.route("/api/status")
def api_status():
    return jsonify(state.snapshot())


@app.route("/api/logs")
def api_logs():
    limit = int(request.args.get("limit", 200))
    return jsonify(fetch_events(limit=limit))


@app.route("/api/logs/clear", methods=["POST"])
def api_logs_clear():
    clear_events()
    return jsonify({"ok": True})


@app.route("/api/logs/export")
def api_logs_export():
    csv_data = export_csv()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=safevessel_logs.csv"},
    )


def start_background_worker():
    global _started
    if _started:
        return
    _started = True
    init_db()
    if SIMULATE:
        threading.Thread(target=run_simulation_loop, args=(_stop_event,), daemon=True).start()
    else:
        threading.Thread(
            target=run_serial_loop, args=(SERIAL_PORT, SERIAL_BAUD, _stop_event), daemon=True
        ).start()


start_background_worker()

if __name__ == "__main__":
    mode = "SIMULATION" if SIMULATE else f"serie ({SERIAL_PORT} @ {SERIAL_BAUD} bauds)"
    print(f"SafeVessel dashboard — mode {mode} — http://0.0.0.0:{HTTP_PORT}")
    app.run(host="0.0.0.0", port=HTTP_PORT, debug=False)
