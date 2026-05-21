import pytest

from gateway.upload_writer import MaxSizeExceeded, UploadWriter


def test_writes_chunks(tmp_path):
    target = tmp_path / "j1" / "upload.bin"
    w = UploadWriter(target, max_bytes=1024)
    w.write(b"hello ")
    w.write(b"world")
    w.close()
    assert target.read_bytes() == b"hello world"
    assert w.total_bytes == 11


def test_creates_parent_dir(tmp_path):
    target = tmp_path / "nested" / "deep" / "upload.bin"
    w = UploadWriter(target, max_bytes=100)
    w.write(b"x")
    w.close()
    assert target.exists()


def test_max_size_raises(tmp_path):
    w = UploadWriter(tmp_path / "u.bin", max_bytes=5)
    w.write(b"12345")
    with pytest.raises(MaxSizeExceeded):
        w.write(b"6")
    w.close()


def test_close_idempotent(tmp_path):
    w = UploadWriter(tmp_path / "u.bin", max_bytes=10)
    w.write(b"abc")
    w.close()
    w.close()  # should not raise
