"""
Database layer for Virtuyal.

This module defines SQLAlchemy models and helper functions to read/write
devices, sensor time series, users, roles, and SMTP configuration.

Docstrings use Google style so they can be parsed by doxypypy for inclusion in
Doxygen-generated documentation. Timestamps are stored in UTC unless noted.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import functions
import models
from flask import jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import time
# Removed thread-based timeouts; we'll rely on tinytuya socket timeouts for simplicity and speed
import socket
import os

db = SQLAlchemy()

#=================================
# sensorData table
#=================================
class SensorDataModel(db.Model):
    __tablename__ = 'data'

    """Sensor time-series data captured from Tuya devices.

    Columns:
        DataID (int): Surrogate primary key.
        Timestamp (datetime): Record timestamp in UTC.
        HCHO (float): Formaldehyde concentration (device raw scaled by /1000).
        AQI (str): Air quality level stored as a numeric string (1..3).
        CO2 (int): CO2 ppm.
        CO (int): CO value.
        TVOC (float): Total Volatile Organic Compounds (raw scaled by /1000).
        Temperature (int): Temperature (unit depends on device setting).
        Humidity (int): Relative humidity percent.
        PM2_5 (int): PM2.5 value.
        PM1 (int): PM1.0 value.
        PM10 (int): PM10 value.
        PM0_3 (int): PM0.3 value.
        Device_DataID (str): Foreign key to device ID (string).
    """

    DataID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Store UTC by default. Using datetime.utcnow ensures naive UTC stored in DB.
    Timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    HCHO = db.Column(db.Float, nullable=False)
    AQI = db.Column(db.String(15), nullable=False)
    CO2 = db.Column(db.Integer, nullable=False)
    CO = db.Column(db.Integer, nullable=False)
    TVOC = db.Column(db.Float, nullable=False)
    Temperature = db.Column(db.Integer, nullable=False)
    Humidity = db.Column(db.Integer, nullable=False)
    PM2_5 = db.Column(db.Integer, nullable=False)
    PM1 = db.Column(db.Integer, nullable=False)
    PM10 = db.Column(db.Integer, nullable=False)
    PM0_3 = db.Column(db.Integer, nullable=False)
    Device_DataID = db.Column(db.String(45), nullable=False)

def insert_sensor_data(sensorData, device_id):
    """Insert a new sensor data record.

    Notes:
      - AQI is stored as a numeric level extracted from values like "level_1".
      - HCHO and TVOC device raw values (e.g., 23) are stored scaled (/1000 -> 0.023).

    Args:
        sensorData (models.SensorData): Instance containing sensor readings.
        device_id (str): Device identifier.

    Returns:
        bool: True if committed successfully, False otherwise.
    """
    # Translate AQI levels
    aqi_raw = getattr(sensorData, "aqi", "")
    aqi_map = {"level_1": "Gut", "level_2": "Mittelmäßig", "level_3": "Schlecht"}
    aqi_translated = aqi_map.get(aqi_raw, aqi_raw)
    data = SensorDataModel(
        # HCHO device raw value e.g. 23 should be stored as 0.023
        HCHO=(float(getattr(sensorData, "hcho", 0)) / 1000.0),
        AQI=functions.extract_number(getattr(sensorData, "aqi", 0)),
        CO2=int(getattr(sensorData, "co2", 0)),
        CO=int(getattr(sensorData, "co", 0)),
        # TVOC device raw value e.g. 23 should be stored as 0.023
        TVOC=(float(getattr(sensorData, "tvoc", 0)) / 1000.0),
        Temperature=int(getattr(sensorData, "temp", 0)),
        Humidity=int(getattr(sensorData, "hum", 0)),
        PM2_5=int(getattr(sensorData, "pm2_5", 0)),
        PM1=int(getattr(sensorData, "pm1_0", 0)),
        PM10=int(getattr(sensorData, "pm10", 0)),
        PM0_3=int(getattr(sensorData, "pm0_3", 0)),
        Device_DataID=device_id
    )
    try:
        db.session.add(data)
        db.session.commit()
        print(f"Data inserted successfully.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error inserting data: {e}")
        return False

#=================================
# device table
#=================================
class DeviceInfoModel(db.Model):
    __tablename__ = 'device'

    """Device registry with LAN connectivity metadata.

    Columns:
        DeviceID (str): Primary key (Tuya device ID).
        Name (str): Human-readable name.
        Status (str): Free-form status flag.
        IPAdress (str): Last known IP address.
        LocalKey (str): Tuya local key for LAN control.
        ClassroomID (str): Location/classroom identifier.
        Active (bool): Soft-delete flag; only active devices are used.
    """

    DeviceID = db.Column(db.String(45), primary_key=True)
    Name = db.Column(db.String(45), nullable=False)
    Status = db.Column(db.String(45), nullable=False)
    IPAdress = db.Column(db.String(45), nullable=False)
    LocalKey = db.Column(db.String(45), nullable=False)
    ClassroomID = db.Column(db.String(5), nullable=False)
    Active = db.Column(db.Boolean, nullable=False, default=True)

    def __str__(self):
        return f"DeviceID: {self.DeviceID}, Name: {self.Name}, Status: {self.Status}, IPAdress: {self.IPAdress}, LocalKey: {self.LocalKey}, ClassroomID: {self.ClassroomID}"

def insert_device(device_id, name, ip_address, local_key, classroom_id):
    """Insert a new device record.

    Args:
        device_id (str): Device identifier.
        name (str): Device name.
        ip_address (str): Device IP address.
        local_key (str): Device local key.
        classroom_id (str): Classroom identifier.

    Returns:
        bool: True if committed successfully, False otherwise.
    """
    tempStatus = True #todo default
    device = DeviceInfoModel(
        DeviceID=device_id,
        Name=name,
        Status=tempStatus,
        IPAdress=ip_address,
        LocalKey=local_key,
        ClassroomID=classroom_id,
        Active=True
    )
    try:
        print("Adding device to DB: ", device)
        db.session.add(device)
        db.session.commit()
        print(f"Device {device_id} inserted successfully.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error inserting device: {e}")
        return False
    
def delete_device(device_id):
    """Soft-delete a device by marking it inactive.

    Args:
        device_id (str): Device identifier.

    Returns:
        bool: True if updated successfully, False otherwise.
    """
    device = DeviceInfoModel.query.get(device_id)
    if not device:
        print(f"Device {device_id} not found.")
        return False
    try:
        device.Active = False
        db.session.commit()
        print(f"Device {device_id} marked inactive.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error marking device inactive: {e}")
        return False 

def get_device_from_db(device_id: str):
    """Retrieve a device as a ``models.Device`` instance.

    Args:
        device_id (str): Device identifier.

    Returns:
        models.Device | None: Device object if found, else None.
    """
    device_entry = None
    try:
        device_entry = DeviceInfoModel.query.get(device_id)
    except Exception as e:
        print(f"Error querying device: {e}")

    if not device_entry:
        print(f"Device {device_id} not found in DB.")
        return None

    device = models.Device(
        device_id=device_entry.DeviceID,
        name=device_entry.Name,
        status=device_entry.Status,
        ip_address=device_entry.IPAdress,
        local_key=device_entry.LocalKey,
        classroom_number=device_entry.ClassroomID
    )
    return device

def get_all_devices():
    """Return all active devices as dictionaries.

    Returns:
        list[dict]: Device dictionaries compatible with API responses.
    """
    t0 = time.perf_counter()
    devices = DeviceInfoModel.query.filter_by(Active=True).all()
    t_query = (time.perf_counter() - t0) * 1000
   
    device_list = []
    checked = 0
    t_checks = time.perf_counter()
    for device_entry in devices:
        checked += 1
        t1 = time.perf_counter()
        tempStatus = check_device_online(device_entry.DeviceID)
        t_online = (time.perf_counter() - t1) * 1000
        print(f"[DB:get_all_devices] check_device_online for {device_entry.DeviceID} took {t_online:.1f} ms -> {tempStatus}")
        device = models.Device(
            device_id=device_entry.DeviceID,
            name=device_entry.Name,
            status=tempStatus,
            ip_address=device_entry.IPAdress,
            local_key=device_entry.LocalKey,
            classroom_number=device_entry.ClassroomID
        )
        device_list.append(device.to_dict())

    return device_list

def does_device_exist(device_id):
    """Check if a device exists.

    Args:
        device_id (str): Device identifier.

    Returns:
        bool: True if exists, False otherwise.
    """
    device = DeviceInfoModel.query.get(device_id)
    return device is not None

def is_device_active(device_id):
    """Check if a device is active.

    Args:
        device_id (str): Device identifier.

    Returns:
        bool | None: True if active, False if inactive, None if not found.
    """
    device = DeviceInfoModel.query.get(device_id)
    if not device:
        return None
    return bool(device.Active)

def get_sensor_history(device_id: str, metric: str, start, end, limit: int = 50000):
    """Retrieve raw time series points for a metric.

    Args:
        device_id (str): Device identifier.
        metric (str): Metric name (e.g., "aqi", "co2").
        start (datetime): Inclusive UTC start.
        end (datetime): Inclusive UTC end.
        limit (int): Maximum number of records to return.

    Returns:
        list[dict]: Items of shape {"ts": ISO-8601 string, "value": number}.
    """
    # map API metric names to DB column attributes
    metric_map = {
        "aqi": "AQI",
        "co": "CO",
        "co2": "CO2",
        "hcho": "HCHO",
        "hum": "Humidity",
        "pm0_3": "PM0_3",
        "pm10": "PM10",
        "pm1_0": "PM1",
        "pm2_5": "PM2_5",
        "temp": "Temperature",
        "tvoc": "TVOC",
    }
    col_name = metric_map.get((metric or "").lower())
    if not col_name:
        return []
    try:
        col = getattr(SensorDataModel, col_name)
    except AttributeError:
        return []

    try:
        q = (SensorDataModel.query
             .with_entities(SensorDataModel.Timestamp, col)
             .filter(SensorDataModel.Device_DataID == device_id)
             .filter(SensorDataModel.Timestamp >= start)
             .filter(SensorDataModel.Timestamp <= end)
             .order_by(SensorDataModel.Timestamp.asc())
             .limit(limit))
        rows = q.all()
        out = []
        for ts, val in rows:
            if ts is None:
                continue
            # AQI is stored as a number (extract_number used on insert); cast numeric values
            out.append({"ts": ts.isoformat(), "value": val})
        return out
    except Exception as e:
        print("get_sensor_history query error:", e)
        return []

def add_device(device_id, name, local_key, classroom_id, ip_address):
    """Add a device; reactivate and update if it exists but is inactive.

    Args:
        device_id (str): Device identifier.
        name (str): Device name.
        local_key (str): Device local key.
        classroom_id (str): Classroom identifier.
        ip_address (str): Device IP address.

    Returns:
        bool: True if inserted/reactivated, False if already active or on error.
    """
    # If device exists and is inactive, reactivate and update fields
    existing = DeviceInfoModel.query.get(device_id)
    if existing:
        if existing.Active:
            print(f"Device {device_id} already exists and is active.")
            return False
        # Reactivate and update
        existing.Name = name or existing.Name
        existing.LocalKey = local_key or existing.LocalKey
        existing.ClassroomID = classroom_id or existing.ClassroomID
        if ip_address:
            existing.IPAdress = ip_address
        existing.Active = True
        try:
            db.session.commit()
            print(f"Device {device_id} reactivated and updated.")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error reactivating device: {e}")
            return False

    if ip_address is None:
        ip_address = functions.get_ip_from_id(device_id)
        if ip_address is None:
            print(f"Could not find IP address for device {device_id}.")
            return False

    status = True #default
    if not device_id or not name or not status or not local_key or not classroom_id:
        print("Missing required device fields.")
        return False

    return insert_device(device_id, name, ip_address, local_key, classroom_id)

def update_device_ip(device_id, new_ip):
    """Update the IP address of a device.

    Args:
        device_id (str): Device identifier.
        new_ip (str): New IP address.

    Returns:
        bool | None: True if updated, None if not found or on error.
    """
    device = DeviceInfoModel.query.get(device_id)
    if not device:
        print(f"You haven't added device: {device_id} to the database yet.")
        return None

    if new_ip is not None and device.IPAdress != new_ip:
        device.IPAdress = new_ip
        try:
            db.session.commit()
            print(f"Device {device_id} IP updated to {new_ip}.")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating device IP: {e}")
            return None
    print("No IP update needed.")
    return True

def update_device_local_key(device_id, new_local_key):
    """Update the local key of a device.

    Args:
        device_id (str): Device identifier.
        new_local_key (str): New local key.

    Returns:
        bool | None: True if updated, None if not found or on error.
    """
    device = DeviceInfoModel.query.get(device_id)
    if not device:
        print(f"Device {device_id} not found.")
        return None

    if new_local_key is not None and device.LocalKey != new_local_key:
        device.LocalKey = new_local_key
        try:
            db.session.commit()
            print(f"Device {device_id} Local Key updated to {new_local_key}.")
        except Exception as e:
            db.session.rollback()
            print(f"Error updating device Local Key: {e}")
            return None
    return True

def edit_sensor(device_id: str, name: str = None, room: str = None):
    """Update sensor metadata for the given device.

    Only 'name' and 'room' (ClassroomID) are editable.

    Args:
        device_id (str): Device identifier.
        name (str | None): New device name.
        room (str | None): New classroom ID.

    Returns:
        bool: True on success, False if not found or on error.
    """
    device = DeviceInfoModel.query.get(device_id)
    if not device:
        print(f"Device {device_id} not found.")
        return False

    if name is None and room is None:
        print("Nothing to update (both name and room are None).")
        return False

    try:
        if name is not None:
            device.Name = name
        if room is not None:
            device.ClassroomID = room
        db.session.commit()
        print(f"Device {device_id} updated (name/room).")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error updating device {device_id}: {e}")
        return False

def get_curr_sensor_data(device_id):
    """Retrieve current sensor data via Tuya and normalize values.

    Performs a quick TCP preflight to short-circuit if the device appears
    offline. Returns a Flask JSON response of the form
    {"success": true, "data": {...}} or an error payload.

    Args:
        device_id (str): Device identifier to fetch data from.

    Returns:
        flask.Response: JSON response indicating success or error details.
    """
    t0 = time.perf_counter()
    device = get_device_from_db(device_id)
    if not device:
        print(f"Device {device_id} not found in DB.")
        return jsonify({ "success": False, "error": "Device not found in DB" })
    try:
        # Quick TCP preflight: if device IP is not reachable on Tuya port, bail out fast
        try:
            ip = getattr(device, 'ip_address', None)
            if ip:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    result = s.connect_ex((ip, 6668))
                    if result != 0:
                        print(f"[DB:get_curr_sensor_data] Preflight TCP connect failed for {device_id} @ {ip} (rc={result}); marking offline")
                        return jsonify({ "success": False, "error": "Device is offline or not responding" })
        except Exception as _e:
            # Ignore preflight errors; proceed to Tuya status
            pass

        tuyaDevice = models.Device.to_tinytuya_device(device)
        # Best-effort: reduce socket time spent inside tinytuya if supported
        try:
            if hasattr(tuyaDevice, "set_socketTimeout"):
                tuyaDevice.set_socketTimeout(3.0)
            if hasattr(tuyaDevice, "set_socketRetryCount"):
                tuyaDevice.set_socketRetryCount(0)
            if hasattr(tuyaDevice, "set_socketRetryDelay"):
                tuyaDevice.set_socketRetryDelay(0.2)
        except Exception:
            pass

        t_status0 = time.perf_counter()
        raw_status = tuyaDevice.status()
        t_status = (time.perf_counter() - t_status0) * 1000
        if "Error" in raw_status:
            print(f"Error: {raw_status.get('Error')} - {raw_status.get('Err')}")
            return jsonify({ "success": False, "ErrorCode": raw_status.get("Err"), "ErrorMessage": raw_status.get("Error")})
        if "dps" in raw_status:
            dps = raw_status["dps"]
        elif "data" in raw_status and "dps" in raw_status["data"]:
            dps = raw_status["data"]["dps"]
        else:
            dps = {}
            
        # If all sensor values are zero or dps is empty, consider the device offline
        if not dps or all(value == 0 for value in dps.values()):
            print(f"Device {device_id} appears to be offline (all values zero or no data).")
            return jsonify({ "success": False, "error": "Device is offline" })
            
        sensorData = models.SensorData(dps)
        # Translate AQI in the output as well
        data_dict = sensorData.to_dict()
        aqi_map = {"level_1": "Gut", "level_2": "Mittelmäßig", "level_3": "Schlecht"}
        if "aqi" in data_dict:
            data_dict["aqi"] = aqi_map.get(data_dict["aqi"], data_dict["aqi"])
        # Fixed precision for small-concentration metrics (ignore env var)
        # Use higher precision so values like 0.00025 are visible in responses
        SENSOR_DECIMALS = 6
        # Scale HCHO to decimals for API response (e.g., 23 -> 0.023)
        if "hcho" in data_dict and data_dict["hcho"] is not None:
            try:
                data_dict["hcho"] = round(float(data_dict["hcho"]) / 1000.0, SENSOR_DECIMALS)
            except Exception:
                pass
        # Scale TVOC to decimals for API response
        if "tvoc" in data_dict and data_dict["tvoc"] is not None:
            try:
                data_dict["tvoc"] = round(float(data_dict["tvoc"]) / 1000.0, SENSOR_DECIMALS)
            except Exception:
                pass
        dt_total = (time.perf_counter() - t0) * 1000
        return jsonify({ "success": True, "data": data_dict})
    except Exception as e:
        dt_total = (time.perf_counter() - t0) * 1000
        print(f"[DB:get_curr_sensor_data] Exception for {device_id} after {dt_total:.1f} ms: {e}")
        return jsonify({ "success": False, "error": str(e)})

#if getcurr_sensor_data returns 0 values then the device is offline
def check_device_online(device_id):
    """Determine if a device is online using current data.

    A device is considered online if any important sensor field contains a
    non-zero/non-empty value.

    Args:
        device_id (str): Device identifier.

    Returns:
        bool: True if online, False otherwise.
    """
    t0 = time.perf_counter()
    response = get_curr_sensor_data(device_id)
    data = response.get_json()
    print(f"[DB:check_device_online] Data for {device_id}: success={data.get('success') if isinstance(data, dict) else 'n/a'}")
    if data and data.get("success") and data.get("data"):
        sensor_data = data["data"]
        important_fields = ["hcho", "aqi", "co2", "tvoc", "temp", "hum", "pm2_5", "pm1_0", "pm10", "pm0_3"]
        # For 'aqi', which is a string, you might want to check it's not empty or not 'level_0'
        if any(
            (sensor_data.get(field, 0) != 0 if field != "aqi" else sensor_data.get("aqi") not in [None, "", "level_0"])
            for field in important_fields
        ):
            dt = (time.perf_counter() - t0) * 1000
            print(f"[DB:check_device_online] Device {device_id} is ONLINE (took {dt:.1f} ms)")
            return True
    dt = (time.perf_counter() - t0) * 1000
    print(f"[DB:check_device_online] Device {device_id} is OFFLINE or no valid data received (took {dt:.1f} ms)")
    return False

#==================
# User table
#==================
class UserDataModel(db.Model):
    __tablename__ = 'user'

    """User accounts and preferences.

    Columns:
        UserID (int): Surrogate primary key.
        UserName (str): Username.
        UserEmail (str): Email address (unique in practice).
        UserPassword (str): Password hash (Werkzeug).
        Roles_RoleID (int): Foreign key to roles.RoleID.
        ThresholdWarning (bool): Opt-in for threshold exceed emails.
        ForgotPasswordCode (int | None): Last set reset code.
        ForgotPasswordCodeSetAt (datetime | None): When reset code was set.
    """

    UserID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    UserName = db.Column(db.String(45), nullable=False)
    UserEmail = db.Column(db.String(45), nullable=False)
    UserPassword = db.Column(db.String(255), nullable=False)
    Roles_RoleID = db.Column(
        db.Integer,
        db.ForeignKey('roles.RoleID'),
        nullable=False
    )
    # Whether the user wants to receive threshold exceed warning emails
    ThresholdWarning = db.Column(db.Boolean, nullable=False, default=False)
    ForgotPasswordCode = db.Column(db.Integer, nullable=True) # 5-digit int, can be null
    ForgotPasswordCodeSetAt = db.Column(db.DateTime, nullable=True) # timestamp when the code was set, can be null

def does_user_exist(email):
    """Check if a user with the given email exists.

    Args:
        email (str): User email address.

    Returns:
        bool: True if the user exists, False otherwise.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if user:
        print(f"User with email {email} exists.")
        return True 
    #else
    print(f"User with email {email} does not exist.")
    return False

def get_user_email(email):
    """Retrieve a user's email if the user exists.

    Args:
        email (str): Email to search for.

    Returns:
        str | None: The stored email if found, else None.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if user:
        print(f"User {user.UserName} found with email {user.UserEmail}.")
        return user.UserEmail
    print(f"User with email {email} not found.")
    return None

def get_user_by_username(username):
    """Retrieve a user record by username.

    Args:
        username (str): The username to search for.

    Returns:
        UserDataModel | None: The user record if found, else None.
    """
    user = UserDataModel.query.filter_by(UserName=username).first()
    if user:
        print(f"User {username} found.")
        return user
    print(f"User {username} not found.")
    return None

def role_name_from_id(role_id):
    """Resolve a role name given its ID.

    Args:
        role_id (int): The role identifier.

    Returns:
        str | None: The role name if found, else None.
    """
    role = RoleDataModel.query.get(role_id)
    if role:
        return role.RoleName
    return None

def get_role_name_from_email(email):
    """Get the role name for a user identified by email.

    Args:
        email (str): User email address.
    Returns:
        str | None: Role name if user found, else None.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if not user:
        print(f"User with email {email} not found.")
        return None
    role = RoleDataModel.query.get(user.Roles_RoleID)
    if role:
        return role.RoleName
    return None

def change_user_role(email, new_role_id):
    """Change the role of the user identified by email.

    Args:
        email (str): Email of the user whose role should be changed.
        new_role_id (int): Target role ID.

    Returns:
        bool: True on success, False if user or role not found.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if not user:
        print(f"User with email {email} not found.")
        return False
    role = RoleDataModel.query.get(new_role_id)
    if not role:
        print(f"Role with ID {new_role_id} not found.")
        return False
    user.Roles_RoleID = role.RoleID
    db.session.commit()
    print(f"Successfully changed the role from user: '{email}' to {user.Roles_RoleID} ({role_name_from_id(user.Roles_RoleID)})")
    return True

def get_all_users():
    """Retrieve all users, projecting to email, username, and role name.

    Returns:
        list[dict]: Items include keys 'email', 'username', and 'role'.
    """
    users = UserDataModel.query.all()
    result = []
    for user in users:
        role = RoleDataModel.query.get(user.Roles_RoleID)
        result.append({
            "email": user.UserEmail,
            "username": user.UserName,
            "role": role_name_from_id(user.Roles_RoleID)
        })
    return result

def get_threshold_recipients():
    """Return user emails that opted in to threshold warnings.

    Returns:
        list[str]: Email addresses.
    """
    try:
        users = UserDataModel.query.filter_by(ThresholdWarning=True).all()
        return [u.UserEmail for u in users]
    except Exception as e:
        print("get_threshold_recipients error:", e)
        return []

def set_threshold_warning(email: str, enabled: bool) -> bool:
    """Enable/disable threshold warning emails for a user.

    Args:
        email (str): User email.
        enabled (bool): True to enable, False to disable.

    Returns:
        bool: True on success, False if user not found or on error.
    """
    try:
        user = UserDataModel.query.filter_by(UserEmail=email).first()
        if not user:
            print(f"User with email {email} not found.")
            return False
        user.ThresholdWarning = bool(enabled)
        db.session.commit()
        print(f"Set ThresholdWarning={enabled} for {email}")
        return True
    except Exception as e:
        db.session.rollback()
        print("set_threshold_warning error:", e)
        return False

def create_user(username, email, password):
    """Create a new user with the given credentials.

    Defaults role to guest (RoleID=2). Caller should ensure uniqueness rules
    (API checks email uniqueness before calling).

    Args:
        username (str): Desired username.
        email (str): User email address.
        password (str): Plain-text password (will be hashed before storing).

    Returns:
        bool: True if created, False if existing or on error.
    """

    user = UserDataModel(
        UserName=username,
        UserEmail=email,
        UserPassword=generate_password_hash(password),
        #standard guest
        Roles_RoleID=2
    )

    if does_user_exist(username):
        print(f"User {username} already exists.")
        return False
    try:
        db.session.add(user)
        db.session.commit()
        print(f"User {username} created successfully.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error creating user: {e}")
        return False

def delete_user(username):
    """Delete a user by username.

    Args:
        username (str): Username identifying the user to delete.

    Returns:
        bool: True on success, False if not found or on error.
    """
    user = UserDataModel.query.filter_by(UserName=username).first()
    if not user:
        print(f"User {username} not found.")
        return False
    try:
        db.session.delete(user)
        db.session.commit()
        print(f"User {username} deleted successfully.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting user: {e}")
        return False

def delete_user_by_email(email):
    """Delete a user by email.

    Args:
        email (str): Email identifying the user to delete.

    Returns:
        bool: True on success, False if not found or on error.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if not user:
        print(f"User with email {email} not found.")
        return False
    try:
        db.session.delete(user)
        db.session.commit()
        print(f"User with email {email} deleted successfully.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting user by email: {e}")
        return False

def verify_user_password(email, password):
    """Verify a user's password by email using a secure hash comparison.

    Args:
        email (str): User email address.
        password (str): Plain-text password to verify.

    Returns:
        bool: True if password matches, False otherwise.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if not user:
        print(f"User with email {email} not found.")
        return False
    if check_password_hash(user.UserPassword, password):
        print(f"Password for user {user.UserName} is correct.")
        return True
    return False

#forgot password functions
def set_forgot_password_code(email):
    """Set a 5-digit password reset code for the user.

    Stores the code and set timestamp in UTC.

    Args:
        email (str): Email of the user requesting password reset.

    Returns:
        int | None: The reset code if set, None if user not found.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if not user:
        print(f"User not found.")
        return None
    code = functions.generate_5_digit_code()
    user.ForgotPasswordCode = code
    # Use UTC for consistency
    user.ForgotPasswordCodeSetAt = datetime.utcnow()
    db.session.commit()
    print("Forgot password code set for user:", user.UserName)
    return code

def reset_user_password(email, reset_code, new_password):
    """Reset a user's password using a valid reset code.

    Args:
        email (str): User email address.
        reset_code (int): The 5-digit code previously set for the user.
        new_password (str): The new plain-text password (will be hashed).

    Returns:
        bool: True on success, False on invalid code/user or DB error.
    """
    user = UserDataModel.query.filter_by(UserEmail=email).first()
    if not user:
        print(f"User with email {email} not found.")
        return False
    if user.ForgotPasswordCode is None:
        print(f"No reset code set or reset code expired for user {user.UserName}.")
        return False
    if user.ForgotPasswordCode != reset_code:
        print(f"Invalid reset code for user {user.UserName}.")
        return False
    user.UserPassword = generate_password_hash(new_password)
    user.ForgotPasswordCode = None
    user.ForgotPasswordCodeSetAt = None
    try:
        db.session.commit()
        print(f"Password for user {user.UserName} has been reset.")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error resetting password: {e}")
        return False

# def set_2fa_code_for_user(user):
#     if not user:
#         print(f"User {user.UserName} not found.")
#         return None
#     print(f"Generating 2fa code for user: {user.UserName}")
#     code = functions.generate_2fa_code()
#     # Use UTC for 2FA expiry as well
#     expiry = datetime.utcnow() + timedelta(minutes=10)
#     user.TwoFaCode = code
#     user.TwoFaExpiry = expiry
#     db.session.commit()
#     return code
#
# def verify_2fa_code(username, code):
#     user = UserDataModel.query.filter_by(UserName=username).first()
#     if not user:
#         print(f"User {username} not found.")
#         return False
#     if user.TwoFaCode == code and user.TwoFaExpiry > datetime.now():
#         user.TwoFaCode = None
#         user.TwoFaExpiry = None
#         db.session.commit()
#         return True
#     return False

#=================================
# roles table
#=================================
class RoleDataModel(db.Model):
    __tablename__ = 'roles'

    """User roles.

    Columns:
        RoleID (int): Primary key.
        RoleName (str): Role display name.
    """

    RoleID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    RoleName = db.Column(db.String(45), nullable=False)

#=================================
# smtp_config table (single-row config)
#=================================
class SmtpConfigModel(db.Model):
    __tablename__ = 'smtp_config'

    """Single-row SMTP configuration.

    Columns:
        ID (int): Primary key, fixed to 1.
        Server (str): SMTP server hostname.
        Port (int): SMTP port.
        CreatedAt (datetime): Creation timestamp (UTC).
        UpdatedAt (datetime): Last update timestamp (UTC).
    """

    ID = db.Column(db.Integer, primary_key=True, default=1)
    Server = db.Column(db.String(255), nullable=False)
    Port = db.Column(db.Integer, nullable=False)
    CreatedAt = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    UpdatedAt = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

def get_smtp_config():
    """Return the SMTP server and port.

    Reads from the smtp_config table; if no row exists, falls back to
    environment variables (SMTP_HOST/SMTP_PORT) or sensible defaults.

    Returns:
        dict: {"server": str, "port": int}
    """
    try:
        row = SmtpConfigModel.query.get(1)
        if row:
            return {"server": row.Server, "port": int(row.Port)}
    except Exception as e:
        print("get_smtp_config error:", e)

    # Fallbacks if table empty or query failed
    server = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    try:
        port = int(os.getenv("SMTP_PORT") or 465)
    except Exception:
        port = 465
    return {"server": server, "port": port}

def set_smtp_config(server: str, port: int) -> bool:
    """Upsert the single-row SMTP config (ID=1).

    Args:
        server (str): SMTP server hostname.
        port (int): SMTP port number (1-65535).

    Returns:
        bool: True on success, False otherwise.
    """
    if not server or not isinstance(server, str):
        print("set_smtp_config: invalid server")
        return False
    try:
        p = int(port)
        if p <= 0 or p > 65535:
            raise ValueError("port out of range")
    except Exception:
        print("set_smtp_config: invalid port")
        return False

    try:
        row = SmtpConfigModel.query.get(1)
        if not row:
            row = SmtpConfigModel(ID=1, Server=server.strip(), Port=p)
            db.session.add(row)
        else:
            row.Server = server.strip()
            row.Port = p
        db.session.commit()
        print(f"SMTP config set to {row.Server}:{row.Port}")
        return True
    except Exception as e:
        db.session.rollback()
        print("set_smtp_config error:", e)
        return False
