"""API startup initialization.

Ensures admin client exists on first run.
"""

import logging
import secrets

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import ApiClient, ApiClientStatus
from .auth import generate_api_key, hash_api_key

logger = logging.getLogger(__name__)


def ensure_admin_client() -> None:
    """Ensure admin client exists.

    This function is called on API startup to create the initial
    admin client if none exists.

    On first run, generates a new admin API key, stores its bcrypt
    hash in the database, and outputs the plain key to terminal ONCE.

    The key cannot be retrieved later - use 'admin reset' to generate
    a new key if forgotten.
    """
    db: Session = SessionLocal()
    try:
        # Check if admin client already exists
        admin = db.query(ApiClient).filter(
            ApiClient.permissions.contains(["admin"])
        ).first()

        if admin:
            logger.info("Admin client already exists")
            return

        # Generate new admin key
        plain_key = generate_api_key()
        hashed_key = hash_api_key(plain_key)

        # Create admin client
        client_id = f"cli_{secrets.token_hex(8)}"

        admin = ApiClient(
            client_id=client_id,
            name="Administrator",
            api_key=hashed_key,
            status=ApiClientStatus.ACTIVE,
            permissions=["admin", "read"],
            description="System administrator (auto-created on first run)",
        )

        db.add(admin)
        db.commit()
        db.refresh(admin)

        logger.info(f"Created admin client: {client_id}")

        # Output key to terminal ONCE
        print(f"\n{'='*60}")
        print("Admin client created successfully.")
        print(f"{'='*60}")
        print(f"\n  Admin API Key: {plain_key}\n")  # nosec B105: intentional display for initial setup
        print("  IMPORTANT: This key is shown ONCE. Save it securely now!")
        print("  If lost, use './scripts/cyber-pulse.sh admin reset' to generate a new key.")
        print(f"\n{'='*60}\n")

    except Exception as e:
        logger.error(f"Failed to ensure admin client: {e}")
        db.rollback()
        raise
    finally:
        db.close()
