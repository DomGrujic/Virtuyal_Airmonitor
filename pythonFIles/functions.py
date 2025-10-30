"""
Utility and API helper functions for Virtuyal.

This module contains Tuya device helpers, history aggregation, email sending,
and small utilities used by the Flask API. Docstrings follow Google style so
they can be converted by doxypypy into Doxygen-friendly comments.
"""

import datetime
import tinytuya
import db
from dotenv import load_dotenv
import os
import smtplib
import socket
import ssl
from contextlib import contextmanager
from email.mime.text import MIMEText
import random
import models
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    class _NoColor:
        def __getattr__(self, name):
            return ""
    Fore = _NoColor()
    Style = _NoColor()

# Fixed decimal places for aggregated series in history responses
# Always use higher precision so tiny values (e.g., 0.00025) are visible; ignore env variable
AGG_DECIMALS = 6

def _now_utc():
    """
    Get the current time as a timezone-aware UTC datetime.

    Returns:
        datetime.datetime: Current UTC time (tz-aware).
    """
    return datetime.datetime.now(datetime.timezone.utc)

#verify password: 8 characters, at least one uppercase, one lowercase, one digit
def is_valid_password(password: str) -> bool:
    """
    Validate a password against basic complexity rules.

    Rules:
    - At least 8 characters
    - Contains at least one uppercase letter, one lowercase letter, and one digit

    Args:
        password (str): Password to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    import re
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    return True

def extract_number(value):
    """
    Extract the first integer number found in a string.

    Example:
        "level_1" -> 1

    Args:
        value (str): Input string to scan.

    Returns:
        int: Extracted integer, or 0 if none found.
    """
    import re
    match = re.search(r'\d+', str(value))
    return int(match.group()) if match else 0

#translate level to text
def level_to_text(level):
    """
    Translate a numeric level (1-3) to a descriptive German text.

    Args:
        level (int): Numeric level in [1..3].

    Returns:
        str: "Gut", "Mittelmäßig", "Schlecht", or "Unknown".
    """
    level_mapping = {
        1: "Gut",
        2: "Mittelmäßig",
        3: "Schlecht",
    }
    return level_mapping.get(level, "Unknown")

def initialize_device(device):
    """
    Initialize and return a tinytuya Device instance from a models.Device.

    Args:
        device (models.Device): Device metadata from the database.

    Returns:
        tinytuya.Device: Configured Tuya device (protocol 3.5).
    """
    tuya_device = tinytuya.Device(device.DeviceID, device.IPAdress, device.LocalKey)
    tuya_device.set_version(3.5)
    device = tuya_device
    return device

#1 minuten device scan
def device_scan(update: bool = False):
    """
    Scan the local network for Tuya devices.

    Args:
        update (bool): If True, update known device IPs in the database.

    Returns:
        list[dict]: List of {"ip": str, "id": str} for discovered devices.
    """
    print("Scanning for Tuya devices...")
    scanned_devices = tinytuya.deviceScan()
    print(f"Scan complete. Found {len(scanned_devices)} devices.")
    result = []
    for ip, info in scanned_devices.items():
        device_id = info.get("id")
        result.append({"ip": ip, "id": device_id})
        if update:
            db.update_device_ip(device_id, ip)
        print(f"Found device - ID: {device_id}, IP: {ip}")
    return result

def get_ip_from_id(device_id):
    """
    Find the IP address for a given Tuya device ID by performing a network scan.

    Args:
        device_id (str): Tuya device identifier.

    Returns:
        str | None: IP address if found, otherwise None.
    """
    ip_address = None
    device_scan_result = device_scan()
    for device in device_scan_result:
        if device.get("id") == device_id:
            ip_address = device.get("ip")
            print("Found IP address for device ID", device_id, ":", ip_address)
            break

    return ip_address

def period_to_range(period: str):
    """
    Convert a relative period into a UTC time window.

    Supported periods: "hour", "day", "week", "month", "year".
    The window spans [now - delta, now].

    Args:
        period (str): Relative period name.

    Returns:
        tuple[datetime.datetime | None, datetime.datetime | None, str | None]:
            (start, end, normalized_period) or (None, None, None) on invalid input.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    period = (period or "").lower()
    mapping = {
        "hour": datetime.timedelta(hours=1),
        "day": datetime.timedelta(days=1),
        "week": datetime.timedelta(days=7),
        "month": datetime.timedelta(days=30),
        "year": datetime.timedelta(days=365),
    }
    delta = mapping.get(period)
    if not delta:
        return None, None, None
    return now - delta, now, period


def parse_iso8601(s: str):
    """
    Parse an ISO-8601 datetime string into a tz-aware UTC datetime.

    Accepts trailing 'Z' as UTC and normalizes any timezone to UTC.

    Args:
        s (str): String to parse.

    Returns:
        datetime.datetime | None: Parsed datetime in UTC, or None on failure.
    """
    if not s:
        return None
    try:
        dt = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        # ensure tz-aware in UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        else:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt
    except Exception:
        return None


def bucket_start(dt: datetime.datetime, granularity: str) -> datetime.datetime:
    """
    Normalize a datetime to the start of a bucket boundary.

    Args:
        dt (datetime.datetime): Input datetime (naive implies UTC).
        granularity (str): "minute", "hour", or any other -> "day".

    Returns:
        datetime.datetime: Bucket-aligned datetime (tz-aware).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    if granularity == "minute":
        return dt.replace(second=0, microsecond=0)
    if granularity == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    # default to day
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)

def _ceil_to_bucket(dt: datetime.datetime, granularity: str) -> datetime.datetime:
    """
    Ceil a datetime to the next bucket boundary when not already aligned.

    Args:
        dt (datetime.datetime): Input datetime.
        granularity (str): "minute", "hour", or other -> "day".

    Returns:
        datetime.datetime: Boundary-aligned datetime.
    """
    b = bucket_start(dt, granularity)
    if granularity == "minute":
        return b if dt == b else b + datetime.timedelta(minutes=1)
    if granularity == "hour":
        return b if dt == b else b + datetime.timedelta(hours=1)
    return b if dt == b else b + datetime.timedelta(days=1)


def aggregate_series(series: list, period: str, start: datetime.datetime = None, end: datetime.datetime = None, fill_missing: bool = False):
    """
    Aggregate raw points into per-bucket averages.

    Input points format: {"ts": str|datetime, "value": number}
    - hour -> minute buckets
    - day/week -> hourly buckets
    - month/year -> daily buckets

    If fill_missing is True and a window [start, end] is given, returns continuous buckets
    with empty buckets reported as {"avg": None, "n": 0}.

    Args:
        series (list): Raw points to aggregate.
        period (str): One of "hour", "day", "week", "month", "year".
        start (datetime.datetime | None): Start of the window (UTC).
        end (datetime.datetime | None): End of the window (UTC).
        fill_missing (bool): Whether to include empty buckets in the output.

    Returns:
        tuple[str, list[dict]]: (granularity, aggregated_points), where each point is
        {"ts": iso8601, "avg": float|None, "n": int}.
    """
    period_l = (period or "").lower()
    if period_l == "hour":
        granularity = "minute"
    elif period_l in ("day", "week"):
        granularity = "hour"
    else:
        granularity = "day"
    sums = {}
    counts = {}
    for p in series or []:
        ts = p.get("ts")
        val = p.get("value")
        if val is None or ts is None:
            continue
        if isinstance(ts, str):
            dt = parse_iso8601(ts)
            if dt is None:
                try:
                    dt = datetime.datetime.fromisoformat(ts)
                except Exception:
                    continue
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=datetime.timezone.utc)
        elif isinstance(ts, datetime.datetime):
            dt = ts if ts.tzinfo else ts.replace(tzinfo=datetime.timezone.utc)
        else:
            continue
        b = bucket_start(dt, granularity)
        key = b.isoformat()
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        sums[key] = sums.get(key, 0.0) + fval
        counts[key] = counts.get(key, 0) + 1

    # If not filling gaps or no window provided, return only non-empty buckets
    if not fill_missing or not start or not end:
        out = []
        for key in sorted(sums.keys()):
            total = sums[key]
            n = counts[key]
            avg = round(total / n, AGG_DECIMALS) if n else None
            out.append({"ts": key, "avg": avg, "n": n})
        return granularity, out

    # Build a continuous bucket timeline for [start, end] inclusive of the end bucket
    start_iter = _ceil_to_bucket(start, granularity)
    end_anchor = bucket_start(end, granularity)  # last included bucket start
    if granularity == "minute":
        step = datetime.timedelta(minutes=1)
    elif granularity == "hour":
        step = datetime.timedelta(hours=1)
    else:
        step = datetime.timedelta(days=1)

    if start_iter > end_anchor:
        return granularity, []

    out = []
    cur = start_iter
    while cur <= end_anchor:
        key = cur.isoformat()
        n = counts.get(key, 0)
        avg = round(sums[key] / n, AGG_DECIMALS) if n else None
        out.append({"ts": key, "avg": avg, "n": n})
        cur += step
    return granularity, out

# ------------------
# API helpers moved from api.py
# (pydoc generation function removed per project cleanup)
# ------------------

def build_history_response(device_id: str, metric: str, period: str):
    """
    Build a standardized history API response for a device/metric/period.

    Validates input, fetches raw points from the DB, aggregates into bucket averages,
    and fills missing buckets for the selected window.

    Args:
        device_id (str): Device identifier.
        metric (str): Metric name (e.g., "tvoc").
        period (str): One of "day", "week", "month", "year".

    Returns:
        tuple[dict, int]: (JSON-serializable payload, HTTP status code).
    """
    allowed_metrics = {
        "aqi","co","co2","hcho","hum","pm0_3","pm10","pm1_0","pm2_5","temp","tvoc"
    }
    m = (metric or "").strip().lower()
    if m not in allowed_metrics:
        return {"success": False, "error": "Invalid metric"}, 400

    start_dt, end_dt, p = period_to_range(period)
    if not start_dt:
        return {"success": False, "error": "Invalid period. Use day|week|month|year"}, 400
    if not db.does_device_exist(device_id):
        return {"success": False, "error": "Device not found"}, 404

    raw = db.get_sensor_history(device_id, m, start_dt, end_dt)
    granularity, data = aggregate_series(raw, p, start=start_dt, end=end_dt, fill_missing=True)

    data_wo_n = [{"ts": d.get("ts"), "avg": d.get("avg")} for d in (data or [])]

    return {
        "success": True,
        "device_id": device_id,
        "metric": m,
        "period": p,
        "granularity": granularity,
        "count": len(data_wo_n),
        "data": data_wo_n,
        "message": "No data for the selected range" if not data_wo_n else None
    }, 200

VALUE_TRESHOLDS = {
    "aqi": "Schlecht",
    "hum": 70,
    "co2": 1400,
    "pm2_5": 50,
    "pm10": 80,
    "tvoc": 1,
    "co": 2,
    "hcho": 0.12,
    "pm0_3": 80,
    "pm0_1": 30
}

LAST_ALERT_EMAIL_SENT = None

def check_thresholds_and_alert(sensor):
    """
    Check sensor values against VALUE_TRESHOLDS and send email alerts to opted-in users.

    Uses a simple global anti-spam window of 10 minutes between alert batches.

    Args:
        sensor (models.SensorData): Parsed sensor data object.

    Returns:
        None
    """
    global LAST_ALERT_EMAIL_SENT
    alerts = []
    for key, threshold in VALUE_TRESHOLDS.items():
        sensor_value = getattr(sensor, key, None)
        if sensor_value is not None:
            if isinstance(threshold, str):
                if sensor_value == threshold:
                    alerts.append(f"{key.upper()} level is {sensor_value}, which exceeds the threshold of {threshold}.")
            else:
                try:
                    sensor_value_float = float(sensor_value)
                    if sensor_value_float >= threshold:
                        alerts.append(f"{key.upper()} value is {sensor_value_float}, which exceeds the threshold of {threshold}.")
                except (TypeError, ValueError):
                    continue
    # Anti-spam: only send if last email was >10 minutes ago
    now = datetime.datetime.now(datetime.timezone.utc)
    if alerts:
        if LAST_ALERT_EMAIL_SENT is None or (now - LAST_ALERT_EMAIL_SENT).total_seconds() > 600:
            alert_message = "\n".join(alerts)
            subject = f"Sensor Alert for {getattr(sensor, 'device_id', 'device')}"
            try:
                recipients = db.get_threshold_recipients()
            except Exception as e:
                print("Failed to load threshold recipients:", e)
                recipients = []
            if not recipients:
                print("No recipients with ThresholdWarning enabled; not sending alert.")
            else:
                for addr in recipients:
                    try:
                        send_mail(addr, subject, alert_message)
                    except Exception as e:
                        print(f"Error sending alert to {addr}:", e)
                LAST_ALERT_EMAIL_SENT = now
        else:
            print("Alert email suppressed to prevent spam (last sent <10min ago).")

# 2-minute periodic data collection (no threshold emails)
def two_minute_update():
    """
    Collect and store sensor data for all devices.

    Intended for periodic execution (e.g., every 2 minutes).

    Returns:
        None
    """
    from api import app  # import here for no circular import
    with app.app_context():
        devices = db.DeviceInfoModel.query.filter_by(Active=True).all()
        print(f"[collector] Starting pass for {len(devices)} active device(s)")
        for device in devices:
            device_id = getattr(device, 'DeviceID', None)
            try:
                # Initialize tinytuya device and fetch status
                tuya_device = initialize_device(device)
                raw_status = tuya_device.status()
                if isinstance(raw_status, dict) and "Error" in raw_status:
                    print(f"[collector] {device_id}: Tuya error {raw_status.get('Err')} {raw_status.get('Error')}")
                    continue
                # Extract DPS payload in a robust way
                if isinstance(raw_status, dict):
                    if "dps" in raw_status:
                        dps = raw_status.get("dps", {})
                    elif "data" in raw_status and isinstance(raw_status["data"], dict):
                        dps = raw_status["data"].get("dps", {})
                    else:
                        dps = {}
                else:
                    dps = {}

                # Consider device offline if empty or all zeros
                if not dps or all((v == 0 or v is None) for v in dps.values()):
                    print(f"[collector] {device_id}: no DPS or all zeros -> offline, skipping")
                    # still heartbeat to keep connection fresh
                    try:
                        tuya_device.heartbeat()
                    except Exception:
                        pass
                    continue

                # Build sensor from DPS
                sensor = models.SensorData(dps)
                # Translate AQI text for consistency
                if hasattr(sensor, "aqi"):
                    aqi_map = {"level_1": "Gut", "level_2": "Mittelmäßig", "level_3": "Schlecht"}
                    sensor.aqi = aqi_map.get(sensor.aqi, sensor.aqi)

                # Insert into DB directly (avoid redundant online check that re-queries the device)
                ok = db.insert_sensor_data(sensor, device_id)
                if ok:
                    print(f"[collector] {device_id}: data saved to DB")
                else:
                    print(f"[collector] {device_id}: DB insert failed")

                # Threshold checks after saving
                check_thresholds_and_alert(sensor)

                # Keep-alive
                try:
                    tuya_device.heartbeat()
                except Exception:
                    pass
            except Exception as e:
                print(f"[collector] {device_id}: error collecting sensor data: {e}")

#MAIL FUNCTION
load_dotenv()
USER = os.getenv("MAIL_USER")
PASS = os.getenv("MAIL_PASS")
print("Loaded user:", USER)

def send_mail(to_email, subject, body):
    """
    Send a plain-text email via SMTP (Gmail by default).

    Args:
        to_email (str): Recipient email address.
        subject (str): Email subject line.
        body (str): Email body text.

    Returns:
        bool: True on success, False otherwise.
    """
    if not USER or not PASS:
        print("error: MAIL_USER or MAIL_PASS not set in .env")
        return False
    
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = USER
    msg["To"] = to_email

    try:
        print("Connecting to Gmail SMTP...")
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.set_debuglevel(1)
            server.starttls()
            server.login(USER, PASS)
            server.sendmail(USER, [to_email], msg.as_string())
            print("Mail sent successfully to", to_email)
            return True
    except smtplib.SMTPAuthenticationError as e:
        print("Authentication failed: wrong username/password or app password missing")
        print("Details:", e)
    except Exception as e:
        print("Failed to send mail:", str(e))
    return False

def send_code_email(to_email, subject, body, code):
    """
    Send a styled HTML email containing a short verification code.

    Tries implicit SSL (465) or STARTTLS (587) based on configuration and network conditions.
    Performs optional IPv4-only resolution to avoid IPv6 TLS issues on some networks.

    Args:
        to_email (str): Recipient email address.
        subject (str): Email subject line.
        body (str): Additional explanatory text to include in the message.
        code (str | int): Verification code to display prominently.

    Returns:
        bool: True on success, False otherwise.
    """
    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 40px;">
        <div style="max-width: 400px; margin: auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); padding: 32px;">
          <h2 style="text-align: center; color: #333;">Your Virtuyal 2FA Code</h2>
          <div style="text-align: center; margin: 32px 0;">
            <span style="font-size: 2.5em; font-weight: bold; letter-spacing: 0.2em; color: #0078d4; background: #f0f4fa; padding: 16px 32px; border-radius: 8px; display: inline-block;">
              {code}
            </span>
          </div>
          <p style="text-align: center; color: #555;">{body}</p>
        </div>
      </body>
    </html>
    """

    if not USER or not PASS:
        print("error: MAIL_USER or MAIL_PASS not set in .env")
        return False
    
    msg = MIMEText(html_body, "html")
    msg["Subject"] = subject
    msg["From"] = USER
    msg["To"] = to_email

    # Diagnostic: show DNS resolution for smtp.gmail.com
    try:
        infos = socket.getaddrinfo("smtp.gmail.com", None)
        unique_ips = sorted({i[4][0] for i in infos if i and i[4]})
        print("smtp.gmail.com resolves to:", ", ".join(unique_ips))
    except Exception as e:
        print("DNS resolution error for smtp.gmail.com:", e)

    @contextmanager
    def _force_ipv4_resolution():
        """Temporarily prefer IPv4 addresses to avoid IPv6 blackholes causing TLS timeouts."""
        orig = socket.getaddrinfo
        def ga(host, port, family=0, type=0, proto=0, flags=0):
            res = orig(host, port, family, type, proto, flags)
            v4 = [r for r in res if r and r[0] == socket.AF_INET]
            return v4 or res
        socket.getaddrinfo = ga
        try:
            yield
        finally:
            socket.getaddrinfo = orig

    force_ipv4 = os.getenv("EMAIL_FORCE_IPV4", "1").strip().lower() not in ("0", "false", "no")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com"
    prefer_465 = os.getenv("EMAIL_PREFER_465", "1").strip().lower() not in ("0", "false", "no")
    try:
        smtp_timeout = float(os.getenv("EMAIL_SMTP_TIMEOUT", "10"))
        if smtp_timeout <= 0:
            smtp_timeout = 10.0
    except Exception:
        smtp_timeout = 10.0

    # If DB provides SMTP settings, use them and set preferred port accordingly
    try:
        cfg = db.get_smtp_config()
        if isinstance(cfg, dict):
            host_db = (cfg.get("server") or "").strip()
            port_db = int(cfg.get("port") or 0)
            if host_db:
                smtp_host = host_db
            if port_db in (465, 587):
                prefer_465 = (port_db == 465)
            print(f"Using SMTP from DB: {smtp_host}:{port_db if port_db else '(default)'} (prefer_465={prefer_465})")
    except Exception as e:
        print("Failed to load SMTP config from DB, using env/defaults:", e)
    if force_ipv4:
        print("Forcing IPv4 resolution for SMTP connections")
    else:
        print("Using default IPv4/IPv6 resolution for SMTP connections")

    def _send_via_587():
        print("Trying to send 2FA code email via STARTTLS on 587...")
        with smtplib.SMTP(smtp_host, 587, timeout=smtp_timeout) as server:
            server.set_debuglevel(1)
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(USER, PASS)
            server.sendmail(USER, [to_email], msg.as_string())

    def _send_via_465():
        print("Trying SMTP_SSL on 465...")
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, 465, context=context, timeout=smtp_timeout) as server:
            server.set_debuglevel(1)
            server.login(USER, PASS)
            server.sendmail(USER, [to_email], msg.as_string())

    # Try preferred order; default is 465 first (many networks block STARTTLS but allow implicit SSL)
    order = ("465", "587") if prefer_465 else ("587", "465")
    last_err = None
    for port in order:
        try:
            cm = _force_ipv4_resolution() if force_ipv4 else contextmanager(lambda: (yield))()
            with cm:
                if port == "465":
                    _send_via_465()
                    print("Email sent successfully via 465.")
                else:
                    _send_via_587()
                    print("Email sent successfully via 587.")
            return True
        except Exception as e:
            last_err = e
            print(f"Send via {port} failed:", e)
    print("Both SMTP attempts failed:", last_err)
    return False

#generate 5 digit code
def generate_5_digit_code():
    """
    Generate a random 5-digit numeric code.

    Returns:
        int: Value in the range [10000..99999].
    """
    return random.randint(10000, 99999)
