"""API startup initialization.

Ensures admin client exists on first run.
"""

import logging
import os
import secrets

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import ApiClient, ApiClientStatus
from .auth import ApiClientService, generate_api_key, hash_api_key

logger = logging.getLogger(__name__)


def ensure_admin_client() -> None:
    """Ensure admin client exists.

    This function is called on API startup to create the initial
    admin client if none exists.

    The admin API key is taken from ADMIN_API_KEY environment variable,
    or generated if not set.
    """
    db: Session = SessionLocal()
    try:
        service = ApiClientService(db)
        admin = service.get_by_permission("admin")

        if admin:
            logger.info("Admin client already exists")
            return

        # Get or generate admin key
        admin_key = os.getenv("ADMIN_API_KEY")
        if not admin_key:
            admin_key = generate_api_key()
            logger.warning(
                "ADMIN_API_KEY not set, generated new key. "
                "Set ADMIN_API_KEY environment variable for reproducible deployments."
            )

        # Create admin client
        client_id = f"cli_{secrets.token_hex(8)}"
        hashed_key = hash_api_key(admin_key)

        admin = ApiClient(
            client_id=client_id,
            name="Administrator",
            api_key=hashed_key,
            status=ApiClientStatus.ACTIVE,
            permissions=["admin", "read"],
            description="System administrator (auto-created)",
        )

        db.add(admin)
        db.commit()
        db.refresh(admin)

        logger.info(f"Created admin client: {client_id}")
        # Note: API key is not logged for security reasons.
        # The admin key should be retrieved from ADMIN_API_KEY env var or .env file.
        print(f"\n{'='*60}")
        print("Admin client created successfully.")
        print("Check ADMIN_API_KEY in .env file for the API key.")
        print(f"{'='*60}\n")

    except Exception as e:
        logger.error(f"Failed to ensure admin client: {e}")
        db.rollback()
        raise
    finally:
        db.close()