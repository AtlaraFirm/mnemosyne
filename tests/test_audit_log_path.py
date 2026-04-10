import os
import pytest
from mnemosyne.services import writes

def test_audit_log_path_rejects_outside(tmp_path):
    os.environ["VAULT_PATH"] = str(tmp_path)
    # Set audit log path outside the vault directory
    outside_path = tmp_path.parent / "outside_audit.log"
    os.environ["AUDIT_LOG_PATH"] = str(outside_path)
    plan = writes.create_note("OutsideTitle", "Body")
    # Should raise ValueError
    with pytest.raises(ValueError, match="audit_log_path must be inside the vault directory"):
        writes.apply_plan(plan)

def test_audit_log_path_accepts_inside(tmp_path):
    os.environ["VAULT_PATH"] = str(tmp_path)
    inside_path = tmp_path / "audit.log"
    os.environ["AUDIT_LOG_PATH"] = str(inside_path)
    os.environ["AUDIT_LOG_PATH"] = str(inside_path)
    os.environ["VAULT_PATH"] = str(tmp_path)
    plan = writes.create_note("InsideTitle", "Body")
    # Should not raise
    writes.apply_plan(plan)
    assert inside_path.exists()
