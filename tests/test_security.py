import os
import sys

import pytest

from mgua2.security.keyfile import validate_key_path
from mgua2.security.redaction import KEY_MARK, PATH_MARK, TOKEN_MARK, VIN_MARK, mask_vin, redact, redact_args

VIN = "WBS12345678901234"


def test_vin_redacted():
    out = redact(f"VIN {VIN} ok")
    assert VIN not in out and VIN_MARK in out


def test_vin_arg_nonstandard():
    assert "SHORT1" not in redact("flash --vin SHORT1")


def test_mask_vin():
    m = mask_vin(VIN)
    assert m.startswith("WBS") and m.endswith("34") and VIN not in m


def test_tokens():
    tok = "ghp_" + "A" * 36
    assert tok not in redact(f"Authorization: token {tok}") and TOKEN_MARK in redact(tok)


def test_private_key_block():
    blk = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
    out = redact("a\n" + blk + "\nb")
    assert "MIIEowIBAAKCAQEA" not in out and KEY_MARK in out and "a" in out


def test_redact_args():
    out = redact_args(["x", "--vin", VIN, "--identity", "/k/id_rsa", "--identity=/s/k"])
    s = " ".join(out)
    assert VIN not in s and "/k/id_rsa" not in s and "/s/k" not in s and VIN_MARK in out and PATH_MARK in out


def test_idempotent():
    once = redact(f"{VIN} ghp_" + "C" * 36)
    assert redact(once) == once


def test_key_missing_dir_ok(tmp_path):
    assert not validate_key_path(tmp_path / "nope").ok
    assert not validate_key_path(tmp_path).ok
    k = tmp_path / "id_rsa"
    k.write_text("x")
    if not sys.platform.startswith("win"):
        os.chmod(k, 0o600)
    assert validate_key_path(k).ok


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX")
def test_key_world_readable(tmp_path):
    k = tmp_path / "id_rsa"
    k.write_text("x")
    os.chmod(k, 0o644)
    assert not validate_key_path(k).ok
