from cyberpulse.models import Source, Item, Content, ApiClient
from cyberpulse.models import SourceTier, SourceStatus, ItemStatus, ContentStatus, ApiClientStatus


def test_models_import():
    """Test that all models can be imported"""
    assert Source is not None
    assert Item is not None
    assert Content is not None
    assert ApiClient is not None


def test_source_tier_enum():
    """Test SourceTier enum values"""
    assert SourceTier.T0 == "T0"
    assert SourceTier.T1 == "T1"
    assert SourceTier.T2 == "T2"
    assert SourceTier.T3 == "T3"


def test_source_status_enum():
    """Test SourceStatus enum values"""
    assert SourceStatus.ACTIVE == "ACTIVE"
    assert SourceStatus.FROZEN == "FROZEN"
    assert SourceStatus.REMOVED == "REMOVED"


def test_item_status_enum():
    """Test ItemStatus enum values"""
    assert ItemStatus.NEW == "NEW"
    assert ItemStatus.NORMALIZED == "NORMALIZED"
    assert ItemStatus.MAPPED == "MAPPED"
    assert ItemStatus.REJECTED == "REJECTED"


def test_content_status_enum():
    """Test ContentStatus enum values"""
    assert ContentStatus.ACTIVE == "ACTIVE"
    assert ContentStatus.ARCHIVED == "ARCHIVED"


def test_api_client_status_enum():
    """Test ApiClientStatus enum values"""
    assert ApiClientStatus.ACTIVE == "ACTIVE"
    assert ApiClientStatus.SUSPENDED == "SUSPENDED"
    assert ApiClientStatus.REVOKED == "REVOKED"


def test_item_status_default_is_enum():
    """Test that Item.status uses ItemStatus enum"""
    # Verify the column type is Enum
    from sqlalchemy import Enum as SAEnum
    from cyberpulse.models.item import Item
    status_col = Item.__table__.c.status
    assert isinstance(status_col.type, SAEnum)
    assert status_col.type.name == "itemstatus"


def test_content_status_default_is_enum():
    """Test that Content.status uses ContentStatus enum"""
    from sqlalchemy import Enum as SAEnum
    from cyberpulse.models.content import Content
    status_col = Content.__table__.c.status
    assert isinstance(status_col.type, SAEnum)
    assert status_col.type.name == "contentstatus"


def test_api_client_status_default_is_enum():
    """Test that ApiClient.status uses ApiClientStatus enum"""
    from sqlalchemy import Enum as SAEnum
    from cyberpulse.models.api_client import ApiClient
    status_col = ApiClient.__table__.c.status
    assert isinstance(status_col.type, SAEnum)
    assert status_col.type.name == "apiclientstatus"


def test_source_uses_enum_types():
    """Test that Source model uses Enum types for tier and status"""
    from sqlalchemy import Enum as SAEnum
    from cyberpulse.models.source import Source
    tier_col = Source.__table__.c.tier
    status_col = Source.__table__.c.status
    assert isinstance(tier_col.type, SAEnum)
    assert isinstance(status_col.type, SAEnum)
    assert tier_col.type.name == "sourcetier"
    assert status_col.type.name == "sourcestatus"