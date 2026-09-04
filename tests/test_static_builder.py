import pandas as pd
import pytest

from scripts.build_static_dashboard import (
    as_bool,
    require_columns,
    require_unique,
    safe_text,
)


def test_static_builder_normalises_booleans_and_escapes_text():
    assert as_bool(True)
    assert as_bool("TRUE")
    assert not as_bool("False")
    assert not as_bool(float("nan"))
    assert safe_text("<script>alert(1)</script>") == (
        "&lt;script&gt;alert(1)&lt;/script&gt;"
    )
    assert safe_text(float("nan")) == "—"


def test_static_builder_schema_guards_fail_loudly():
    frame = pd.DataFrame({"record_id": ["a", "a"]})
    with pytest.raises(ValueError, match="missing required columns"):
        require_columns(frame, "example.csv", {"record_id", "value"})
    with pytest.raises(ValueError, match="unique rows"):
        require_unique(frame, "example.csv", ["record_id"])
