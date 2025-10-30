"""
Data models for Tuya devices and sensor readings.

This module provides lightweight classes used by the API layer to translate
between database/device structures and application-friendly objects.

Docstrings follow Google style so they can be parsed by doxypypy and included
in Doxygen-generated documentation.
"""

import tinytuya


class Device:
    """Represents a Tuya device known to the system.

    Attributes:
        device_id (str): Unique device identifier.
        name (str): Human-readable device name.
        status (str|int|None): Optional status flag or text.
        ip_address (str|None): Last known IP address.
        local_key (str|None): Tuya local key required for LAN control.
        classroom_number (int|str|None): Classroom/location reference.
        version (str): Tuya protocol version used for LAN control.
    """
    def __init__(
        self, device_id, name, status, ip_address, local_key, classroom_number
    ):
        """Initialize a Device.

        Args:
            device_id (str): Unique device identifier.
            name (str): Device name.
            status (str|int|None): Optional status value.
            ip_address (str|None): Last known IP address.
            local_key (str|None): Tuya local key.
            classroom_number (int|str|None): Classroom/location reference.
        """
        self.device_id = device_id
        self.name = name
        self.status = status
        self.ip_address = ip_address
        self.local_key = local_key
        self.classroom_number = classroom_number
        self.version = "3.5"

    def __str__(self):
        """Return a concise, human-readable summary of the device."""
        return f"Device(ID: {self.device_id}, Name: {self.name}, Status: {self.status}, IP: {self.ip_address}, Classroom: {self.classroom_number})"

    def to_dict(self):
        """Serialize this device into a dictionary compatible with DB field names.

        Returns:
            dict: Mapping with keys matching database column names.
        """
        return {
            "DeviceID": self.device_id,
            "Name": self.name,
            "Status": self.status,
            "Classrooms_ClassroomNumber": self.classroom_number,
        }

    @classmethod
    def dict_to_device(device_dict):
        """Convert a dictionary (DB row) to a Device instance.

        Note: Defined as a classmethod for compatibility with existing code,
        but it doesn't use the class reference directly.

        Args:
            device_dict (dict): Dictionary with device info.

        Returns:
            Device: A new Device created from the mapping.
        """
        from db import check_device_online

        tempStatus = check_device_online(device_dict.get("DeviceID"))
        return Device(
            device_id=device_dict.get("DeviceID"),
            name=device_dict.get("Name"),
            status=device_dict.get("Status"),
            ip_address=device_dict.get("IPAdress"),
            local_key=device_dict.get("LocalKey"),
            classroom_number=device_dict.get("Classrooms_ClassroomNumber"),
        )

    @staticmethod
    def to_tinytuya_device(device):
        """Convert a Device object to a ``tinytuya.Device`` instance.

        Args:
            device (Device): Your custom Device object.

        Returns:
            tinytuya.Device: Instance ready for LAN communication.
        """
        tuyaDevice = tinytuya.Device(
            device.device_id, device.ip_address, device.local_key
        )
        tuyaDevice.set_version(3.5)
        return tuyaDevice


SENSOR_MAPPING = {
    1: "AQI",
    2: "TEMP",
    3: "HUM",
    4: "CO2",
    5: "HCHO",
    7: "PM2.5",
    8: "PM1.0",
    9: "PM10",
    22: "Battery level",
    23: "Charging",
    28: "Alarm Volume",
    101: "TVOC",
    102: "CO",
    103: "Brightness",
    104: "CO2 Alarm Value",
    105: "Sleep",
    106: "Alarm",
    107: "PM0.3",
    108: "Timer",
    112: "Temp Unit Converter",
}


class SensorData:
    """Container for sensor readings parsed from Tuya DPS payloads.

    The constructor normalizes DPS keys to Python-friendly attribute names and
    translates certain values (e.g., AQI levels) into human-readable strings.
    """
    def __init__(self, dps):
        """Initialize from a DPS mapping returned by tinytuya.

        Args:
            dps (dict): Raw DPS mapping where keys are string integers and
                values are sensor readings.
        """
        allowed_attrs = {
            "aqi",
            "temp",
            "hum",
            "co2",
            "hcho",
            "pm2_5",
            "pm1_0",
            "pm10",
            "tvoc",
            "co",
            "co2",
            "pm0_3",
        }
        aqi_map = {"level_1": "Gut", "level_2": "Mittelmäßig", "level_3": "Schlecht"}
        for key, value in dps.items():
            try:
                name = SENSOR_MAPPING.get(int(key), f"unknown_{key}")
            except ValueError:
                name = f"unknown_{key}"
            attr = name.lower().replace(" ", "_").replace(".", "_")
            if attr in allowed_attrs:
                # Translate AQI if present
                if attr == "aqi":
                    value = aqi_map.get(value, value)
                setattr(self, attr, value)

    def __str__(self):
        """Return a human-readable list of key=value pairs for debugging."""
        # for console debugging --> prettier output
        d = self.to_dict()
        attrs = [f"{k}={v}" for k, v in d.items()]
        return ", ".join(attrs)

    def to_dict(self):
        """Convert the sensor data to a dictionary.

        Translates AQI codes to German labels if necessary.

        Returns:
            dict: Mapping of normalized attribute names to values.
        """
        d = dict(self.__dict__)
        aqi_map = {"level_1": "Gut", "level_2": "Mittelmäßig", "level_3": "schlecht"}
        aqi = d.get("aqi")
        if isinstance(aqi, str):
            if aqi.startswith("level_"):
                d["aqi"] = aqi_map.get(aqi, aqi)
            else:
                try:
                    num = int(aqi)
                    d["aqi"] = aqi_map.get(num, aqi)
                except Exception:
                    pass
        return d
