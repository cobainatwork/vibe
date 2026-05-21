import pytest

from shared.db import connect, run_migrations
from shared.repositories.hotword_repository import (
    create_group, get_group, get_group_words, list_groups,
    update_group, delete_group, DuplicateNameError, GroupNotFoundError,
)


@pytest.fixture
def conn(tmp_db_path):
    c = connect(tmp_db_path)
    run_migrations(c)
    return c


def test_create_and_get(conn):
    gid = create_group(conn, name="醫療", words=["心電圖", "MRI"])
    g = get_group(conn, gid)
    assert g.name == "醫療"
    assert g.words == ["心電圖", "MRI"]


def test_words_csv_roundtrip_with_commas_escaped(conn):
    # We disallow commas in words for simplicity; verify error
    with pytest.raises(ValueError):
        create_group(conn, name="bad", words=["has,comma"])


def test_duplicate_name_raises(conn):
    create_group(conn, name="g1", words=["a"])
    with pytest.raises(DuplicateNameError):
        create_group(conn, name="g1", words=["b"])


def test_list_groups_sorted(conn):
    create_group(conn, name="b", words=["x"])
    create_group(conn, name="a", words=["y"])
    groups = list_groups(conn)
    assert [g.name for g in groups] == ["a", "b"]


def test_update_group(conn):
    gid = create_group(conn, name="x", words=["w1"])
    update_group(conn, gid, name="x2", words=["w1", "w2"])
    g = get_group(conn, gid)
    assert g.name == "x2"
    assert g.words == ["w1", "w2"]


def test_delete_group(conn):
    gid = create_group(conn, name="del", words=["a"])
    delete_group(conn, gid)
    assert get_group(conn, gid) is None


def test_delete_nonexistent_raises(conn):
    with pytest.raises(GroupNotFoundError):
        delete_group(conn, 999)


def test_get_group_words_by_ids(conn):
    g1 = create_group(conn, name="x", words=["a", "b"])
    g2 = create_group(conn, name="y", words=["c"])
    words = get_group_words(conn, [g1, g2])
    assert set(words) == {"a", "b", "c"}
