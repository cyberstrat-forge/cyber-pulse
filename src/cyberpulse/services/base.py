from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session


class BaseService:
    """Base service class with common utilities"""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create(
        self, model, defaults: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Tuple[Any, bool]:
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
        else:
            params = {**kwargs, **(defaults or {})}
            instance = model(**params)
            self.db.add(instance)
            self.db.commit()
            self.db.refresh(instance)
            return instance, True