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
    assert SourceStatus.ACTIVE == "active"
    assert SourceStatus.FROZEN == "frozen"
    assert SourceStatus.REMOVED == "removed"


def test_item_status_enum():
    """Test ItemStatus enum values"""
    assert ItemStatus.NEW == "new"
    assert ItemStatus.NORMALIZED == "normalized"
    assert ItemStatus.MAPPED == "mapped"
    assert ItemStatus.REJECTED == "rejected"


def test_content_status_enum():
    """Test ContentStatus enum values"""
    assert ContentStatus.ACTIVE == "active"
    assert ContentStatus.ARCHIVED == "archived"


def test_api_client_status_enum():
    """Test ApiClientStatus enum values"""
    assert ApiClientStatus.ACTIVE == "active"
    assert ApiClientStatus.SUSPENDED == "suspended"
    assert ApiClientStatus.REVOKED == "revoked"