"""
Configuration accessor for django-blackbox.
Reads DJANGO_BLACKBOX dict from Django settings with sane defaults.
"""
import re
from collections import ChainMap
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Config:
    """Configuration dataclass with defaults."""

    ENABLED: bool = True
    ADD_REQUEST_ID_HEADER: bool = True
    ADD_INCIDENT_ID_HEADER: bool = True
    EXPOSE_JSON_ERROR_BODY: bool = True
    GENERIC_ERROR_MESSAGE: str = "Something broke on our side. We've logged it. Share the Incident ID with support."
    INCLUDE_INCIDENT_ID_IN_BODY: bool = True
    CAPTURE_STACKTRACE: bool = True
    CAPTURE_RESPONSE_5XX: bool = True
    CAPTURE_EXCEPTIONS: bool = True
    # Status codes to capture incidents for (supports ranges and individual codes)
    # Examples:
    # [500, 501, 502] - specific codes
    # [(500, 599)] - range from 500 to 599
    # [(500, 599), 400] - 5xx range plus 400
    CAPTURE_STATUS_CODES: list[int | tuple[int, int]] = field(
        default_factory=lambda: [(500, 599)]
    )
    IGNORE_PATHS: list[str] = field(default_factory=lambda: [])
    IGNORE_EXCEPTIONS: list[str] = field(default_factory=lambda: [])
    SAMPLE_RATE: float = 1.0
    MAX_BODY_BYTES: int = 2048
    STORE_BODY_CONTENT_TYPES: list[str] = field(
        default_factory=lambda: [
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        ]
    )
    # Whether to mask sensitive data (headers, body fields)
    # Set to False to store all data in original format
    REDACT_SENSITIVE_DATA: bool = True
    # Headers to mask when REDACT_SENSITIVE_DATA is True
    REDACT_HEADERS: list[str] = field(
        default_factory=lambda: ["authorization", "cookie", "set-cookie", "x-api-key"]
    )
    # Body fields to mask when REDACT_SENSITIVE_DATA is True
    REDACT_FIELDS: list[str] = field(
        default_factory=lambda: ["password", "token", "access_token", "refresh_token", "secret", "otp"]
    )
    REDACT_MASK: str = "[REDACTED]"
    USER_RESOLUTION_CALLABLE: str | None = None
    RETENTION_DAYS: int = 90
    DEDUP_WINDOW_SECONDS: int = 300
    FALLBACK_FILE_LOG: bool = True
    FALLBACK_FILE_PATH: str = "server_incidents_fallback.log"
    RETURN_ORIGINAL_500_STATUS: bool = True
    RETURN_400_INSTEAD_OF_500: bool = False
    CUSTOM_ERROR_FORMAT: dict | None = None
    OVERRIDE_500_TEMPLATE: str | None = None
    _compiled_ignore_paths: list[Any] = field(default_factory=list, init=False, repr=False)
    _compiled_ignore_exceptions: list[Any] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        """Compile regex patterns for ignore paths."""
        self._compiled_ignore_paths = [re.compile(p) for p in self.IGNORE_PATHS]
        self._compiled_ignore_exceptions = self.IGNORE_EXCEPTIONS


_config: Config | None = None


def get_conf() -> Config:
    """
    Get the current configuration, loading from Django settings if needed.
    
    Returns:
        Config: The current configuration instance.
    """
    global _config
    if _config is None:
        _reload_config()
    return _config


def _reload_config():
    """Reload configuration from Django settings."""
    global _config
    
    try:
        from django.conf import settings
        user_settings = getattr(settings, "DJANGO_BLACKBOX", {})
    except ImportError:
        user_settings = {}
    
    defaults = {
        "ENABLED": True,
        "ADD_REQUEST_ID_HEADER": True,
        "ADD_INCIDENT_ID_HEADER": True,
        "EXPOSE_JSON_ERROR_BODY": True,
        "GENERIC_ERROR_MESSAGE": "Something broke on our side. We've logged it. Share the Incident ID with support.",
        "INCLUDE_INCIDENT_ID_IN_BODY": True,
        "CAPTURE_STACKTRACE": True,
        "CAPTURE_RESPONSE_5XX": True,
        "CAPTURE_EXCEPTIONS": True,
        "CAPTURE_STATUS_CODES": [(500, 599)],
        "IGNORE_PATHS": [],
        "IGNORE_EXCEPTIONS": [],
        "SAMPLE_RATE": 1.0,
        "MAX_BODY_BYTES": 2048,
        "STORE_BODY_CONTENT_TYPES": [
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        ],
        "REDACT_SENSITIVE_DATA": True,
        "REDACT_HEADERS": ["authorization", "cookie", "set-cookie", "x-api-key"],
        "REDACT_FIELDS": ["password", "token", "access_token", "refresh_token", "secret", "otp"],
        "REDACT_MASK": "[REDACTED]",
        "USER_RESOLUTION_CALLABLE": None,
        "RETENTION_DAYS": 90,
        "DEDUP_WINDOW_SECONDS": 300,
        "FALLBACK_FILE_LOG": True,
        "FALLBACK_FILE_PATH": "server_incidents_fallback.log",
        "RETURN_ORIGINAL_500_STATUS": True,
        "RETURN_400_INSTEAD_OF_500": False,
        "CUSTOM_ERROR_FORMAT": None,
        "OVERRIDE_500_TEMPLATE": None,
    }
    
    config_dict = {**defaults, **user_settings}
    _config = Config(**config_dict)


def reset_config():
    """Reset the cached configuration (useful for testing)."""
    global _config
    _config = None

