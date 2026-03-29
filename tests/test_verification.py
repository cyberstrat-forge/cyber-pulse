"""Tests for verification system.

This module tests the verification scripts and utilities.
"""

import os
import subprocess

import pytest


class TestSourcesYaml:
    """Tests for sources.yaml configuration."""

    def test_sources_yaml_exists(self):
        """Test that sources.yaml exists."""
        assert os.path.exists("sources.yaml"), "sources.yaml file not found"

    def test_sources_yaml_valid_yaml(self):
        """Test that sources.yaml is valid YAML."""
        import yaml
        with open("sources.yaml") as f:
            data = yaml.safe_load(f)
        assert data is not None, "sources.yaml is empty"

    def test_sources_yaml_has_sources(self):
        """Test that sources.yaml has at least one source."""
        import yaml
        with open("sources.yaml") as f:
            data = yaml.safe_load(f)
        assert "sources" in data, "sources.yaml missing 'sources' key"
        assert len(data["sources"]) > 0, "sources.yaml has no sources defined"

    def test_sources_yaml_required_fields(self):
        """Test that each source has required fields."""
        import yaml
        with open("sources.yaml") as f:
            data = yaml.safe_load(f)

        for i, source in enumerate(data.get("sources", [])):
            assert "name" in source, f"Source #{i+1} missing 'name' field"
            assert "connector_type" in source, f"Source '{source.get('name', i+1)}' missing 'connector_type'"
            assert "config" in source, f"Source '{source.get('name', i+1)}' missing 'config'"

    def test_sources_yaml_valid_tier(self):
        """Test that tier values are valid."""
        import yaml
        with open("sources.yaml") as f:
            data = yaml.safe_load(f)

        valid_tiers = {"T0", "T1", "T2", "T3"}
        for source in data.get("sources", []):
            tier = source.get("tier")
            if tier is not None:
                assert tier in valid_tiers, f"Source '{source.get('name')}' has invalid tier: {tier}"


class TestVerifyScript:
    """Tests for verify.sh script."""

    @pytest.fixture
    def verify_script_path(self):
        """Return path to verify.sh."""
        return "scripts/verify.sh"

    def test_verify_script_exists(self, verify_script_path):
        """Test that verify.sh exists."""
        assert os.path.exists(verify_script_path), "verify.sh not found"

    def test_verify_script_executable(self, verify_script_path):
        """Test that verify.sh is executable."""
        assert os.access(verify_script_path, os.X_OK), "verify.sh is not executable"

    def test_verify_script_help(self, verify_script_path):
        """Test that verify.sh --help works."""
        result = subprocess.run(
            ["bash", verify_script_path, "--help"],
            capture_output=True,
            text=True
        )
        assert "Usage:" in result.stdout or "用法" in result.stdout, "verify.sh --help should show usage"

    def test_verify_script_syntax(self, verify_script_path):
        """Test that verify.sh has valid bash syntax."""
        result = subprocess.run(
            ["bash", "-n", verify_script_path],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"verify.sh has syntax errors: {result.stderr}"


class TestMakefileVerifyTargets:
    """Tests for Makefile verify targets."""

    def test_makefile_exists(self):
        """Test that Makefile exists."""
        assert os.path.exists("Makefile"), "Makefile not found"

    def test_makefile_has_verify_target(self):
        """Test that Makefile has verify target."""
        with open("Makefile") as f:
            content = f.read()
        assert "verify:" in content, "Makefile missing 'verify' target"

    def test_makefile_has_verify_report_target(self):
        """Test that Makefile has verify-report target."""
        with open("Makefile") as f:
            content = f.read()
        assert "verify-report:" in content, "Makefile missing 'verify-report' target"
