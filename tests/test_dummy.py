"""Basic dummy tests to verify test suite configuration."""

import claudarama


def test_claudarama_version() -> None:
    """Verify package import and version presence."""
    assert claudarama.__version__ == "0.1.0"
