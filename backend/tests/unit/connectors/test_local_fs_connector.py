from cce.connectors.unstructured.local_fs.connector import LocalFileSystemConnector


def test_local_fs_connector_lists_and_fetches_files(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "one.txt").write_text("alpha beta", encoding="utf-8")

    connector = LocalFileSystemConnector(str(root), source_id="source-1")
    connection = connector.connect()
    assert connection.read_only_verified is True

    listed = connector.list_objects()
    assert listed["objects"][0]["object_id"] == "one.txt"
    assert listed["objects"][0]["source_ref"].endswith("one.txt")
    assert connector.fetch_object("one.txt") == b"alpha beta"

    connector.close()
