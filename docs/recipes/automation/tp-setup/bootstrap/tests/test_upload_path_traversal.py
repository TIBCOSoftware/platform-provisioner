#
# Copyright 2025 Cloud Software Group, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Regression tests for TPSEC-128 (security finding f025): the POST /upload
# endpoint must never write outside its upload folder, regardless of the
# client-supplied filename. Before the fix, file.filename was used raw
# (os.path.splitext preserves directory separators), so a "../../evil.sh"
# relative name or an absolute path escaped upload_folder via os.path.join.
# The fix sanitizes the name with werkzeug.secure_filename and adds a
# realpath containment guard; these tests assert the containment property.
#
# The same TPSEC-128 hardening also (a) preserves the real extension for
# non-ASCII / CJK filenames — secure_filename ASCII-strips, so "名字.flogo" would
# otherwise lose ".flogo" and misclassify the upload — and (b) closes a zip-slip
# in Helper.extract_activation_license (reachable from /upload for a .zip), where
# ZipFile.extractall() would honor a "../../evil" member and escape the folder.
# These tests assert all three properties.

import io
import os
import zipfile

import pytest

import server
from utils.helper import Helper


def _post_upload(client, filename, content=b"payload"):
    data = {"file": (io.BytesIO(content), filename)}
    return client.post("/upload", data=data, content_type="multipart/form-data")


def _assert_nothing_escaped(root_dir, upload_folder):
    """Every file that physically exists under root_dir must live inside upload_folder."""
    real_upload = os.path.realpath(upload_folder)
    for base, _dirs, files in os.walk(root_dir):
        for fn in files:
            full = os.path.realpath(os.path.join(base, fn))
            assert full.startswith(real_upload + os.sep), f"file escaped upload_folder: {full}"


def test_upload_rejects_relative_traversal(tmp_path, monkeypatch):
    # Nest the upload folder deep so a "../.." escape still lands inside tmp_path
    # and can be detected by walking tmp_path (without touching the real FS).
    upload_folder = tmp_path / "a" / "b" / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    resp = _post_upload(client_for(), "../../pwned.sh")
    assert resp.status_code in (200, 400)

    # Nothing may exist outside the upload folder.
    _assert_nothing_escaped(tmp_path, upload_folder)

    # If the write was accepted, the stored name must be flattened (no separators / parent refs).
    if resp.status_code == 200:
        stored = resp.get_json()["filename"]
        assert os.sep not in stored and "/" not in stored and ".." not in stored


def test_upload_rejects_absolute_path(tmp_path, monkeypatch):
    upload_folder = tmp_path / "a" / "b" / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    # An absolute path would make os.path.join discard upload_folder entirely.
    abs_name = str(tmp_path / "abs_pwned.sh")
    resp = _post_upload(client_for(), abs_name)
    assert resp.status_code in (200, 400)

    _assert_nothing_escaped(tmp_path, upload_folder)


def test_upload_accepts_normal_filename(tmp_path, monkeypatch):
    upload_folder = tmp_path / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    resp = _post_upload(client_for(), "myapp.flogo")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filetype"] == "FLOGO"
    # Timestamped name, correct extension, contained in upload_folder.
    assert body["filename"].endswith(".flogo")
    saved = os.path.join(str(upload_folder), body["filename"])
    assert os.path.isfile(saved)
    _assert_nothing_escaped(tmp_path, upload_folder)


def test_upload_preserves_unicode_extension(tmp_path, monkeypatch):
    # secure_filename ASCII-strips, collapsing a CJK stem to nothing and taking
    # the extension with it ("名字.flogo" -> "flogo"). The fix takes the extension
    # from the raw name (allowlisted) so filetype classification still works.
    upload_folder = tmp_path / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    resp = _post_upload(client_for(), "名字.flogo")  # 名字.flogo
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filetype"] == "FLOGO", f"unicode name lost its extension: {body}"
    assert body["filename"].endswith(".flogo")
    _assert_nothing_escaped(tmp_path, upload_folder)


def test_upload_strips_disallowed_extension(tmp_path, monkeypatch):
    # A non-allowlisted extension (e.g. ".sh") is dropped: the stored name carries
    # no dangerous extension and the file is classified UNKNOWN — locks in the
    # ALLOWED_UPLOAD_EXTENSIONS allowlist decision.
    upload_folder = tmp_path / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    resp = _post_upload(client_for(), "evil.sh")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filetype"] == "UNKNOWN"
    assert not body["filename"].endswith(".sh"), f"disallowed extension survived: {body['filename']}"
    assert os.sep not in body["filename"] and "/" not in body["filename"] and ".." not in body["filename"]
    _assert_nothing_escaped(tmp_path, upload_folder)


def test_upload_rejects_blank_filename(tmp_path, monkeypatch):
    # A whitespace-only filename is truthy (so `if file:` is entered) but has no
    # usable name -> the endpoint must reject it with 400 rather than save a file.
    upload_folder = tmp_path / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    resp = _post_upload(client_for(), "   ")
    assert resp.status_code == 400
    assert resp.get_json()["message"] == "No filename provided"
    _assert_nothing_escaped(tmp_path, upload_folder)


def test_upload_empty_stem_falls_back(tmp_path, monkeypatch):
    # A pure non-ASCII name that secure_filename() reduces to nothing must still be
    # accepted, stored under the "upload" fallback stem, and contained (no crash,
    # no 400). Its extension is also non-ASCII here, so filetype is UNKNOWN.
    upload_folder = tmp_path / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    resp = _post_upload(client_for(), "名字")  # secure_filename -> "" -> "upload"
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filename"].startswith("upload_")
    assert body["filetype"] == "UNKNOWN"
    _assert_nothing_escaped(tmp_path, upload_folder)


@pytest.mark.parametrize("filename,expected_type", [
    ("app.ear", "BWCE"),
    ("payload.json", "FLOGO"),
    ("app.flogo", "FLOGO"),
    ("service.jar", "SPRINGBOOT"),
])
def test_upload_filetype_classification(tmp_path, monkeypatch, filename, expected_type):
    # Lock the UPLOAD_EXTENSION_FILETYPE map: each allowlisted extension classifies
    # to its filetype and the file is stored contained. (.zip/ACTIVATION is covered
    # by the extract_activation_license tests since it triggers extraction.)
    upload_folder = tmp_path / "upload"
    monkeypatch.setattr(server.Util, "get_upload_folder", staticmethod(lambda: str(upload_folder)))

    resp = _post_upload(client_for(), filename)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["filetype"] == expected_type
    assert body["filename"].endswith(os.path.splitext(filename)[1])
    _assert_nothing_escaped(tmp_path, upload_folder)


def test_extract_activation_license_rejects_zip_slip(tmp_path):
    # A malicious activation zip whose member escapes the upload dir must be
    # rejected wholesale — nothing may be written outside the folder.
    upload_dir = tmp_path / "a" / "b" / "upload"
    upload_dir.mkdir(parents=True)
    zip_path = upload_dir / "activation.zip"
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        zf.writestr("../../pwned.bin", b"malicious")

    assert Helper.extract_activation_license(str(zip_path)) is False
    # Only the zip itself (inside upload_dir) may exist under tmp_path.
    _assert_nothing_escaped(tmp_path, upload_dir)


def test_extract_activation_license_rejects_symlink_member(tmp_path):
    # A member marked as a symlink (S_IFLNK in external_attr) must be rejected
    # outright, so the guard holds regardless of whether the extractor honors
    # symlinks (defense in depth for the zip-slip-via-symlink vector).
    import stat
    upload_dir = tmp_path / "a" / "b" / "upload"
    upload_dir.mkdir(parents=True)
    zip_path = upload_dir / "activation.zip"
    info = zipfile.ZipInfo("link")  # contained name, but it's a symlink entry
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        zf.writestr(info, "../../etc/passwd")
        zf.writestr("license.bin", b"x")

    assert Helper.extract_activation_license(str(zip_path)) is False
    _assert_nothing_escaped(tmp_path, upload_dir)


def test_extract_activation_license_accepts_valid_zip(tmp_path):
    # A well-formed activation zip still extracts and yields license-file.bin.
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir(parents=True)
    zip_path = upload_dir / "activation.zip"
    with zipfile.ZipFile(str(zip_path), "w") as zf:
        zf.writestr("license.bin", b"LICENSE")

    assert Helper.extract_activation_license(str(zip_path)) is True
    assert (upload_dir / "license-file.bin").is_file()
    _assert_nothing_escaped(tmp_path, upload_dir)


def client_for():
    server.app.config.update(TESTING=True)
    return server.app.test_client()
