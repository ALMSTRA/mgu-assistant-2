import gzip
import hashlib
import zipfile

import pytest

from mgua2.services import download as dl
from mgua2.services.tools import mgu_install_asset_name


def test_parse_sha256sums():
    txt = ("e591b3139204c11b5862c13e2315c3311627bad063c9eaa54b564ec4c223b06b  mgu-install-linux-arm64.gz\n"
           "b041ca29448441d0eebc0273400d777173e620fad6f22b5fe7889a3013ab72bf *mgu-install-windows-x64.exe.gz\n"
           "garbage line\n")
    sums = dl.parse_sha256sums(txt)
    assert sums["mgu-install-windows-x64.exe.gz"].startswith("b041ca29")
    assert sums["mgu-install-linux-arm64.gz"].startswith("e591b313")
    assert len(sums) == 2


def test_sha256_verify(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    dl.verify_sha256(p, hashlib.sha256(b"hello").hexdigest())
    with pytest.raises(dl.DownloadError):
        dl.verify_sha256(p, "0" * 64)


def test_gunzip(tmp_path):
    gz = tmp_path / "a.gz"
    with gzip.open(gz, "wb") as f:
        f.write(b"binary-content")
    out = dl.gunzip_to(gz, tmp_path / "out" / "a.exe")
    assert out.read_bytes() == b"binary-content"


def test_safe_extract_strip_top(tmp_path):
    z = tmp_path / "r.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("repo-main/README.md", "x")
        zf.writestr("repo-main/apps/a/app.json", "{}")
    dest = dl.safe_extract_zip(z, tmp_path / "dest", strip_top=True)
    assert (dest / "README.md").exists() and (dest / "apps" / "a" / "app.json").exists()


def test_safe_extract_blocks_traversal(tmp_path):
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    with pytest.raises(dl.DownloadError):
        dl.safe_extract_zip(z, tmp_path / "dest")
    assert not (tmp_path / "evil.txt").exists()


def test_asset_name_matches_release_naming():
    n = mgu_install_asset_name()
    assert n.startswith("mgu-install-") and n.endswith(".gz")


def test_github_zip_url():
    assert dl.github_zip_url("o", "r") == "https://codeload.github.com/o/r/zip/refs/heads/main"


@pytest.mark.net
def test_real_sha256sums_lists_windows_x64():
    sums = dl.parse_sha256sums(dl.fetch_text("https://github.com/robertnisipeanu/mgu-store/releases/download/installer/SHA256SUMS"))
    assert "mgu-install-windows-x64.exe.gz" in sums and "mgu-install-macos-arm64.gz" in sums
