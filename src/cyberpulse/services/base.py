"""
Base service class with common utilities.
"""
import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Allowed URL schemes for connectors
ALLOWED_SCHEMES = frozenset(["http", "https"])

# Private IP ranges (RFC 1918, RFC 3927, RFC 4193)
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),      # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),   # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918
    ipaddress.ip_network("127.0.0.0/8"),     # Loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local (AWS metadata)
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
    ipaddress.ip_network("fc00::/7"),        # IPv6 private
]


class SSRFError(ValueError):
    """Raised when URL validation fails due to SSRF protection."""
    pass


def validate_url_for_ssrf(url: str, allow_localhost: bool = False) -> str:
    """
    Validate a URL for SSRF protection.

    Checks:
    1. URL scheme is in allowed list (http, https)
    2. Hostname resolves to a public IP (not private/internal)

    Args:
        url: The URL to validate
        allow_localhost: If True, allow localhost/127.0.0.1 (for testing)

    Returns:
        The validated URL (unchanged)

    Raises:
        SSRFError: If URL fails validation
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFError(f"Invalid URL format: {url}") from e

    # Check scheme
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFError(
            f"URL scheme '{parsed.scheme}' not allowed. "
            f"Allowed schemes: {', '.join(ALLOWED_SCHEMES)}"
        )

    # Get hostname
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError(f"URL has no hostname: {url}")

    # Check for localhost variants
    localhost_patterns = ["localhost", "127.0.0.1", "::1", "0.0.0.0"]
    if not allow_localhost:
        if hostname.lower() in localhost_patterns:
            raise SSRFError(f"Access to localhost is not allowed: {hostname}")

    # Try to resolve hostname and check IP
    try:
        # Check if hostname is already an IP address
        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            # Not an IP address, continue with DNS resolution
            pass
        else:
            # hostname is a valid IP - check if it's private
            _check_ip_not_private(ip, allow_localhost)
            return url

        # DNS resolution with protection against DNS rebinding
        # Get all IP addresses for the hostname
        addr_info = socket.getaddrinfo(hostname, parsed.port or 80)

        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                _check_ip_not_private(ip, allow_localhost)
            except ValueError:
                continue  # Skip invalid IPs

    except socket.gaierror as e:
        raise SSRFError(f"Failed to resolve hostname: {hostname}") from e
    except (TimeoutError, socket.herror, OSError) as e:
        # Network/DNS errors - fail closed for security
        raise SSRFError(f"DNS resolution error for {hostname}: {e}") from e
    except SSRFError:
        # Let SSRFError propagate up without wrapping
        raise
    except Exception as e:
        # Unexpected errors - fail closed to prevent SSRF bypass
        logger.error(f"Unexpected error during SSRF validation for {url}: {e}")
        raise SSRFError(f"SSRF validation failed for {url}") from e

    return url


def _check_ip_not_private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_localhost: bool) -> None:
    """Check if an IP address is private/internal."""
    for private_range in PRIVATE_IP_RANGES:
        if ip in private_range:
            if allow_localhost and ip.is_loopback:
                continue
            raise SSRFError(
                f"Access to private IP address is not allowed: {ip}"
            )


class BaseService:
    """Base service class with common utilities"""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create(
        self, model, defaults: dict[str, Any] | None = None, **kwargs
    ) -> tuple[Any, bool]:
        """Get or create a record.

        Args:
            model: The SQLAlchemy model class
            defaults: Default values for creation
            **kwargs: Filter criteria

        Returns:
            Tuple of (instance, created) where created is True if a new record was created
        """
        instance = self.db.query(model).filter_by(**kwargs).first()
        if instance:
            return instance, False

        params = {**kwargs, **(defaults or {})}
        instance = model(**params)
        self.db.add(instance)
        try:
            self.db.commit()
            self.db.refresh(instance)
            return instance, True
        except IntegrityError:
            # Race condition - another request created the record
            self.db.rollback()
            instance = self.db.query(model).filter_by(**kwargs).first()
            if instance:
                return instance, False
            raise
