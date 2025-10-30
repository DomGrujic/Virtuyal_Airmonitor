"""
Flask API for Virtuyal.

This module defines all HTTP routes for sensors, data history, users, and
settings. Route docstrings contain Swagger YAML (after a '---' marker) for
Flasgger. The descriptive text before the YAML is kept concise so it can also
be parsed by doxypypy for inclusion in Doxygen documentation.

Note: Do not modify the Swagger YAML blocks unless changing the API contract.
"""

from flask import Flask, request
import tinytuya
import db
import functions
from models import SensorData
from apscheduler.schedulers.background import BackgroundScheduler
from flasgger import Swagger
import os
import time
from dotenv import load_dotenv
from flask_cors import CORS
import threading
try:
  from werkzeug.middleware.proxy_fix import ProxyFix  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
  ProxyFix = None

app = Flask(__name__)
# When running behind a reverse proxy (e.g., Apache/Nginx), trust X-Forwarded-* headers
# so Flask sees the correct client IP, scheme (http/https), host, and port.
if ProxyFix is not None:
  app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
CORS(app)
# Load database credentials from environment variables
load_dotenv()
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASS}@localhost/virtuyal'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False 
db.db.init_app(app)
#swagger config
app.config['SWAGGER'] = {
    "title": "Virtuyal API",
    "uiversion": 3
}
swagger_template = {
    "info": {
        "title": "Virtuyal API",
        "description": "API for Virtuyal project",
        "version": "1.0.0",
    },
    "tags": [
        {
            "name": "sensor",
            "description": "Operations related to sensor data and devices"
        },
        {
            "name": "data",
            "description": "Operations related to current and historical sensor data"
        },
        {
            "name": "user",
            "description": "Operations related to user management"
        }
        # Add more tag definitions here
    ]
}
Swagger(app, template=swagger_template)

# ------------------
# Background jobs (APScheduler) startup
# ------------------
_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER_STARTED = False
_SCHEDULER = None

def _maybe_start_scheduler():
  """Start APScheduler once per process with sensible guards.

  - In dev with Flask reloader, only start in the reloader child.
  - In production, start unconditionally unless RUN_SCHEDULER=0.
  """
  global _SCHEDULER_STARTED, _SCHEDULER
  with _SCHEDULER_LOCK:
    if _SCHEDULER_STARTED:
      return
    run_flag = os.getenv("RUN_SCHEDULER", "1").strip().lower() not in ("0", "false", "no")
    if not run_flag:
      return
    # If running with Werkzeug reloader in dev, only start in the child process
    try:
      is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
      if app.debug and not is_reloader_child:
        return
    except Exception:
      pass
    try:
      _SCHEDULER = BackgroundScheduler()
      # Collect sensor data every 2 minutes
      _SCHEDULER.add_job(func=functions.two_minute_update, trigger="interval", minutes=2)
      _SCHEDULER.start()
      _SCHEDULER_STARTED = True
      print("[API] BackgroundScheduler started (two_minute_update every 2 minutes)")
    except Exception as e:
      print("[API] Failed to start BackgroundScheduler:", e)

# Start background jobs after app and swagger are initialized
_maybe_start_scheduler()

"""
sensor routes
"""
    
@app.route("/sensor/getCurrentData/<device_id>", methods=["GET"])
def get_current_sensor_data_route(device_id):
    """
    Retrieve the current sensor data for a given device.
    ---
    tags:
      - data
    parameters:
      - name: device_id
        in: path
        type: string
        required: true
        description: The unique identifier of the device
    responses:
      200:
        description: Successful operation
        schema:
          type: object
          properties:
            success:
              type: boolean
            data:
              type: object
              properties:
                aqi:
                  type: string
                co:
                  type: integer
                co2:
                  type: integer
                hcho:
                  type: integer
                hum:
                  type: integer
                pm0_3:
                  type: integer
                pm10:
                  type: integer
                pm1_0:
                  type: integer
                pm2_5:
                  type: integer
                temp:
                  type: integer
                tvoc:
                  type: integer
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      500:
        description: Device communication or server error
        schema:
          type: object
          properties:
            success:
              type: boolean
            ErrorCode:
              type: string
            ErrorMessage:
              type: string
    """
    data = db.get_curr_sensor_data(device_id)
    if isinstance(data, dict) and "ErrorCode" in data and "ErrorMessage" in data:
        return data, 500
    if data is None:
        return {"error": "Device not found"}, 404
    return data, 200

@app.route("/sensor/add", methods=["POST"])
def add_device_to_db_route():
    """
    Adds a new device entry to the database.
    ---
    tags:
      - sensor
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            device_id:
              type: string
            name:
              type: string
            local_key:
              type: string
            classroom_number:
              type: integer
    responses:
      201:
        description: Sensor added successfully to db
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Device already exists or invalid input
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      500:
        description: Failed to add sensor to db
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: Could not find device on the network
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    sensor_info = request.json
    #extract other fields from sensor_info for add_device
    name = sensor_info.get("name")
    local_key = sensor_info.get("local_key")
    classroom_number = sensor_info.get("classroom_number")
    device_id = sensor_info.get("device_id")

    if not device_id and not local_key:
        return {"success": False, "error": "Device ID and local key are required"}, 400

    # Let db.add_device handle existing devices:
    # - If exists and active -> returns False (we'll report 409)
    # - If exists and inactive -> updates fields and returns True
    ip_address = functions.get_ip_from_id(device_id)
    if ip_address is None:
        return {"success": False, "error": "Could not find device on the network"}, 404

    if db.add_device(device_id, name, local_key, classroom_number, ip_address):
        # Created (new) or reactivated (inactive -> active)
        return {"success": True, "message": "Sensor added successfully to db"}, 201
    else:
        # If it already exists and is active, signal a conflict
        if db.does_device_exist(device_id) and db.is_device_active(device_id):
            return {"success": False, "error": "Device already exists and is active"}, 409
        # Otherwise, generic failure
        return {"success": False, "error": "Failed to add sensor to db"}, 500

@app.route("/sensor/delete/<device_id>", methods=["GET"])
def delete_device_route(device_id):
    """
    Deactivates a device.
    ---
    tags:
      - sensor
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
    responses:
      204:
        description: Device deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      500:
        description: Failed to delete device
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    if db.does_device_exist(device_id) is False:
        print("Device does not exist, cannot delete.")
        return {"success": False, "error": "Device not found"}, 404

    if db.delete_device(device_id):
        return {"success": True, "message": "Device deleted successfully"}, 204
    return {"success": False, "error": "Failed to delete device"}, 500

@app.route("/sensor/getAllDevices", methods=["GET"])
def get_all_devices_route():
    """
    Retrieves all devices from the database.
    ---
    tags:
      - sensor
    responses:
      200:
        description: Successful operation
        schema:
          type: object
          properties:
            success:
              type: boolean
            data:
              type: array
              items:
                type: object
                properties:
                  device_id:
                    type: string
                  name:
                    type: string
                  status:
                    type: boolean
                  classroom_number:
                    type: string
      500:
        description: Failed to retrieve devices
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    print("[API:getAllDevices] Gathering all devices...")
    t0 = time.perf_counter()
    devices = db.get_all_devices()
    dt = (time.perf_counter() - t0) * 1000
    try:
        count = len(devices) if isinstance(devices, (list, tuple)) else 0
    except Exception:
        count = 0
    print(f"[API:getAllDevices] Done in {dt:.1f} ms, returned {count} devices")
    if devices is None:
        return {"success": False, "error": "Failed to retrieve devices"}, 500
    return {"success": True, "data": devices}, 200

@app.route("/sensor/edit/<device_id>", methods=["PATCH"])
def edit_sensor_route(device_id):
    """
    Update sensor metadata (name and room) for a device.
    ---
    tags:
      - sensor
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
        description: The unique identifier of the device
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
              description: New display name of the device
            room:
              type: string
              description: New room/classroom identifier (ClassroomID)
    responses:
      200:
        description: Device updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Invalid request (nothing to update)
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      500:
        description: Failed to update device
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    body = request.get_json(silent=True) or {}
    name = body.get("name")
    room = body.get("room")

    if name is None and room is None:
        return {"success": False, "error": "Provide at least one of: name, room"}, 400

    if not db.does_device_exist(device_id):
        return {"success": False, "error": "Device not found"}, 404

    ok = db.edit_sensor(device_id, name=name, room=room)
    if ok:
        return {"success": True, "message": "Device updated successfully"}, 200
    return {"success": False, "error": "Failed to update device"}, 500

#==================
#historie
#==================

@app.route("/sensor/history/hour/<device_id>", methods=["GET"])
def get_history_hour_route(device_id):
    """
    Retrieve aggregated hour history for a metric (per-minute buckets, last 60 minutes).
    ---
    tags:
      - data
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
      - name: metric
        in: query
        required: true
        type: string
        enum: [aqi, co, co2, hcho, hum, pm0_3, pm10, pm1_0, pm2_5, temp, tvoc]
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            success:
              type: boolean
            device_id:
              type: string
            metric:
              type: string
            period:
              type: string
            granularity:
              type: string
            count:
              type: integer
            data:
              type: array
              items:
                type: object
                properties:
                  ts:
                    type: string
                  avg:
                    type: number
            message:
              type: string
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    metric = request.args.get("metric", "")
    return functions.build_history_response(device_id, metric, "hour")

@app.route("/sensor/history/day/<device_id>", methods=["GET"])
def get_history_day_route(device_id):
    """
    Retrieve aggregated day history for a metric (hourly buckets).
    ---
    tags:
      - data
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
      - name: metric
        in: query
        required: true
        type: string
        enum: [aqi, co, co2, hcho, hum, pm0_3, pm10, pm1_0, pm2_5, temp, tvoc]
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            success:
              type: boolean
            device_id:
              type: string
            metric:
              type: string
            period:
              type: string
            granularity:
              type: string
            count:
              type: integer
            data:
              type: array
              items:
                type: object
                properties:
                  ts:
                    type: string
                  avg:
                    type: number
            message:
              type: string
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    metric = request.args.get("metric", "")
    return functions.build_history_response(device_id, metric, "day")

@app.route("/sensor/history/week/<device_id>", methods=["GET"])
def get_history_week_route(device_id):
    """
    Retrieve aggregated week history for a metric (hourly buckets).
    ---
    tags:
      - data
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
      - name: metric
        in: query
        required: true
        type: string
        enum: [aqi, co, co2, hcho, hum, pm0_3, pm10, pm1_0, pm2_5, temp, tvoc]
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            success:
              type: boolean
            device_id:
              type: string
            metric:
              type: string
            period:
              type: string
            granularity:
              type: string
            count:
              type: integer
            data:
              type: array
              items:
                type: object
                properties:
                  ts:
                    type: string
                  avg:
                    type: number
            message:
              type: string
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    metric = request.args.get("metric", "")
    return functions.build_history_response(device_id, metric, "week")

@app.route("/sensor/history/month/<device_id>", methods=["GET"])
def get_history_month_route(device_id):
    """
    Retrieve aggregated month history for a metric (daily buckets).
    ---
    tags:
      - data
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
      - name: metric
        in: query
        required: true
        type: string
        enum: [aqi, co, co2, hcho, hum, pm0_3, pm10, pm1_0, pm2_5, temp, tvoc]
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            success:
              type: boolean
            device_id:
              type: string
            metric:
              type: string
            period:
              type: string
            granularity:
              type: string
            count:
              type: integer
            data:
              type: array
              items:
                type: object
                properties:
                  ts:
                    type: string
                  avg:
                    type: number
            message:
              type: string
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    metric = request.args.get("metric", "")
    return functions.build_history_response(device_id, metric, "month")

@app.route("/sensor/history/year/<device_id>", methods=["GET"])
def get_history_year_route(device_id):
    """
    Retrieve aggregated year history for a metric (daily buckets).
    ---
    tags:
      - data
    parameters:
      - name: device_id
        in: path
        required: true
        type: string
      - name: metric
        in: query
        required: true
        type: string
        enum: [aqi, co, co2, hcho, hum, pm0_3, pm10, pm1_0, pm2_5, temp, tvoc]
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            success:
              type: boolean
            device_id:
              type: string
            metric:
              type: string
            period:
              type: string
            granularity:
              type: string
            count:
              type: integer
            data:
              type: array
              items:
                type: object
                properties:
                  ts:
                    type: string
                  avg:
                    type: number
            message:
              type: string
      400:
        description: Invalid parameters
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: Device not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    metric = request.args.get("metric", "")
    return functions.build_history_response(device_id, metric, "year")

#==================
#user routes
#==================
@app.route("/user/createUser", methods=["POST"])
def create_user_route():
    """
    Creates a new user in the database.
    ---
    tags:
      - user
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            username:
              type: string
            password:
              type: string
            email:
              type: string
    responses:
      201:
        description: User created successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      409:
        description: Username already exists
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      500:
        description: Failed to create user
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    print(request.data)
    user_info = request.get_json()
    username = user_info.get("username")
    password = user_info.get("password")
    email = user_info.get("email")

    #check if user already exists
    if db.does_user_exist(email):
        print("Error: User already exists")
        return {"success": False, "error": "Email already exists"}, 409

    #print for debugging
    print(f"Creating user: {username}, Email: {email}, Password: {(password)}")

    if not functions.is_valid_password(password):
        print("Error: Password does not meet complexity requirements. It must be at least 8 characters long and include uppercase letters, lowercase letters, digits, and special characters.")
        return {"success": False, "error": "Password does not meet complexity requirements"}, 400

    if db.create_user(username, email, password):
        print("User created successfully")
        return {"success": True, "message": "User created successfully"}, 201
    else:
        print("Error: Failed to create user")
        return {"success": False, "error": "Failed to create user"}, 500

@app.route("/user/deleteUser/<email>", methods=["GET"])
def delete_user_route(email):
    """
    Deletes a user from the database by email.
    ---
    tags:
      - user
    parameters:
      - name: email
        in: path
        required: true
        type: string
    responses:
      204:
        description: User deleted successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      500:
        description: Failed to delete user
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    if db.delete_user_by_email(email):
        return {"success": True, "message": "User deleted successfully"}, 204
    else:
        return {"success": False, "error": "Failed to delete user"}, 500

@app.route("/user/validateUser", methods=["POST"])
def validate_user_route():
    """
    Validates user credentials.
    ---
    tags:
      - user
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: User validated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      401:
        description: Invalid email or password
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: User not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    user_info = request.get_json()
    print("User Info: " + str(user_info))
    email = user_info.get("email")
    password = user_info.get("password")
    if not db.does_user_exist(email):
        return {"success": False, "error": "User not found"}, 404

    if db.verify_user_password(email, password):
        # Provide user's role so frontend can set localStorage accurately
        role_name = db.get_role_name_from_email(email)
        resp = {
            "success": True,
            "message": "User validated successfully",
            "user": {"email": email}
        }
        if role_name:
            resp["user"]["role"] = role_name
        return resp, 200
    else:
        return {"success": False, "error": "Invalid email or password"}, 401

@app.route("/user/setThresholdWarning", methods=["POST"])
def set_threshold_warning_route():
    """
    Enable or disable threshold warning emails for a user by email.
    ---
    tags:
      - user
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
              description: The user's email address
            enabled:
              type: boolean
              description: True to enable, False to disable
    responses:
      200:
        description: Preference updated
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Missing or invalid parameters
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: User not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    if email == "":
        return {"success": False, "error": "Email is required"}, 400

    enabled_raw = body.get("enabled")
    # Accept booleans and common string representations
    if isinstance(enabled_raw, bool):
        enabled = enabled_raw
    elif isinstance(enabled_raw, str):
        enabled = enabled_raw.strip().lower() in ("1", "true", "yes", "y", "on")
    elif isinstance(enabled_raw, (int, float)):
        enabled = bool(enabled_raw)
    else:
        return {"success": False, "error": "'enabled' must be boolean"}, 400

    ok = db.set_threshold_warning(email, enabled)
    if not ok:
        # Could be not found or a DB error; treat as 404 if user missing
        if not db.does_user_exist(email):
            return {"success": False, "error": "User not found"}, 404
        return {"success": False, "error": "Failed to update preference"}, 500
    return {"success": True, "message": f"ThresholdWarning set to {enabled} for {email}"}, 200

@app.route("/user/getThresholdRecipients", methods=["GET"])
def threshold_recipients_route():
    """
    Get the list of users who receive threshold warning emails.
    ---
    tags:
      - user
    responses:
      200:
        description: OK
        schema:
          type: object
          properties:
            success:
              type: boolean
            recipients:
              type: array
              items:
                type: string
    """
    recipients = db.get_threshold_recipients()
    return {"success": True, "recipients": recipients}, 200

@app.route("/user/setThresholdRecipient", methods=["POST"])
def set_threshold_recipient_route():
    """
    Enable or disable threshold warning emails for a user by email.
    ---
    tags:
      - user
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
              description: The user's email address
            enabled:
              type: boolean
              description: True to enable, False to disable
    responses:
      200:
        description: Preference updated
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Missing or invalid parameters
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: User not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip()
    if email == "":
        return {"success": False, "error": "Email is required"}, 400

    enabled_raw = body.get("enabled")
    # Accept booleans and common string representations
    if isinstance(enabled_raw, bool):
        enabled = enabled_raw
    elif isinstance(enabled_raw, str):
        enabled = enabled_raw.strip().lower() in ("1", "true", "yes", "y", "on")
    elif isinstance(enabled_raw, (int, float)):
        enabled = bool(enabled_raw)
    else:
        return {"success": False, "error": "'enabled' must be boolean"}, 400

    ok = db.set_threshold_warning(email, enabled)
    if not ok:
        # Could be not found or a DB error; treat as 404 if user missing
        if not db.does_user_exist(email):
            return {"success": False, "error": "User not found"}, 404
        return {"success": False, "error": "Failed to update preference"}, 500
    return {"success": True, "message": f"ThresholdWarning set to {enabled} for {email}"}, 200

@app.route("/user/changeUserRole", methods=["POST"])
def change_user_role_route():
    """
    Changes the role of a user.
    ---
    tags:
      - user
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
              description: The email of the user whose role is to be changed
            new_role_id:
              type: integer
              description: The new role ID to assign
    responses:
      200:
        description: User role changed successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Invalid user or role
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      404:
        description: User or role not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    data = request.get_json()
    email = data.get("email")
    new_role_id = data.get("new_role_id")
    if not email or not new_role_id:
        return {"success": False, "error": "Email or new role ID is missing"}, 400
    if db.change_user_role(email, new_role_id):
        return {"success": True, "message": "User role changed successfully"}, 200
    else:
        return {"success": False, "error": "User or role not found"}, 404

@app.route("/user/getAllUsers", methods=["GET"])
def get_all_users_route():
    """
    Retrieves all users with email, username, and role.
    ---
    tags:
      - user
    responses:
      200:
        description: List of all users
        schema:
          type: object
          properties:
            success:
              type: boolean
            data:
              type: array
              items:
                type: object
                properties:
                  email:
                    type: string
                  username:
                    type: string
                  role:
                    type: string
      500:
        description: Failed to retrieve users
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    users = db.get_all_users()
    if users is not None:
        return {"success": True, "data": users}, 200
    else:
        return {"success": False, "error": "Internal Server Error"}, 500

@app.route("/user/getUserRole/<email>", methods=["GET"])
def get_user_role_by_email_route(email):
    """
    Retrieves the role name (and id) for the given user email.
    ---
    tags:
      - user
    parameters:
      - name: email
        in: path
        required: true
        type: string
        description: The email to look up
    responses:
      200:
        description: Role found
        schema:
          type: object
          properties:
            success:
              type: boolean
            email:
              type: string
            role:
              type: string
            role_id:
              type: integer
      404:
        description: User not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    # Look up by email
    user = db.UserDataModel.query.filter_by(UserEmail=email).first()
    if not user:
        return {"success": False, "error": "User not found"}, 404
    role_id = getattr(user, "Roles_RoleID", None)
    role_name = db.role_name_from_id(role_id) if role_id is not None else None
    return {"success": True, "email": email, "role": role_name, "role_id": role_id}, 200

#==================
# settings routes
#==================
@app.route("/settings/smtp", methods=["GET"])
def get_smtp_settings_route():
    """
    Returns the current SMTP server and port from DB (with env fallback).
    ---
    tags:
      - settings
    responses:
      200:
        description: Current SMTP configuration
        schema:
          type: object
          properties:
            success:
              type: boolean
            server:
              type: string
            port:
              type: integer
    """
    cfg = db.get_smtp_config()
    return {"success": True, "server": cfg.get("server"), "port": cfg.get("port")}, 200

@app.route("/settings/smtp", methods=["POST"])
def set_smtp_settings_route():
    """
    Updates the SMTP server and port.
    ---
    tags:
      - settings
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            server:
              type: string
            port:
              type: integer
    responses:
      200:
        description: Updated successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      400:
        description: Invalid input
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      500:
        description: Persist failed
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    body = request.get_json(silent=True) or {}
    server = body.get("server")
    port = body.get("port")
    if not isinstance(server, str) or not server.strip():
        return {"success": False, "error": "Valid 'server' is required"}, 400
    try:
        port_i = int(port)
        if port_i <= 0 or port_i > 65535:
            raise ValueError()
    except Exception:
        return {"success": False, "error": "Valid 'port' (1-65535) is required"}, 400

    # Ensure tables exist (idempotent)
    try:
        db.db.create_all()
    except Exception:
        pass

    ok = db.set_smtp_config(server.strip(), port_i)
    if not ok:
        return {"success": False, "error": "Failed to update SMTP config"}, 500
    return {"success": True, "message": f"SMTP set to {server.strip()}:{port_i}"}, 200

@app.route("/user/forgotPassword/<email>", methods=["GET"])
def forgot_password_route(email):
    """
    Handles forgot password requests.
    ---
    tags:
      - user
    parameters:
      - name: email
        in: path
        required: true
        type: string
        description: The email address of the user requesting password reset
    responses:
      200:
        description: Password reset email sent successfully
        schema:
          type: object
          properties:
            success:
              type: boolean
            message:
              type: string
      404:
        description: User not found
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
      500:
        description: Failed to send password reset email
        schema:
          type: object
          properties:
            success:
              type: boolean
            error:
              type: string
    """
    if not db.does_user_exist(email):
        return {"success": False, "error": "User not found"}, 404

    reset_code = db.set_forgot_password_code(email)
    if not reset_code:
        return {"success": False, "error": "Failed to set reset code"}, 500

    email_body = f"Your password reset code is: {reset_code}"

    print("Sending password reset email to", email)
    if functions.send_code_email(email, "Password Reset Request", email_body, reset_code):
        return {"success": True, "message": "Password reset email sent successfully"}, 200
    else:
        return {"success": False, "error": "Failed to send password reset email"}, 500

@app.route("/user/resetPassword", methods=["POST"])
def reset_password_route():
    """
    Resets the user's password using a reset code.
    ---
    tags:
      - user
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
            reset_code:
              type: integer
            new_password:
              type: string
    responses:
        200:
            description: Password reset successfully
            schema:
            type: object
            properties:
                success:
                type: boolean
                message:
                type: string
        400:
            description: Invalid reset code or missing parameters
            schema:
            type: object
            properties:
                success:
                type: boolean
                error:
                type: string
        404:
            description: User not found
            schema:
            type: object
            properties:
                success:
                type: boolean
                error:
                type: string
        500:
            description: Failed to reset password
            schema:
            type: object
            properties:
                success:
                type: boolean
                error:
                type: string
        """
    user_info = request.get_json()
    email = user_info.get("email")
    reset_code = user_info.get("reset_code")
    new_password = user_info.get("new_password")

    if not db.does_user_exist(email):
        return {"success": False, "error": "User not found"}, 404

    if not reset_code or not new_password:
        return {"success": False, "error": "Reset code and new password are required"}, 400

    if db.reset_user_password(email, reset_code, new_password):
        return {"success": True, "message": "Password reset successfully"}, 200
    else:
        return {"success": False, "error": "Invalid reset code or failed to reset password"}, 400

#==================
#MAIN
#==================
if __name__ == "__main__":
  # Dev entry-point if running this file directly.
  # Background scheduler is already started above via _maybe_start_scheduler().
  with app.app_context():
        # Optional dev-only utilities can go here.
        pass
        
        app.run(host="127.0.0.1", port=8000)
        