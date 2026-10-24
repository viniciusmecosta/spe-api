from app.shared.storage import resolve_stored_file


def test_storage_blocks_traversal_external_files_and_symlinks(tmp_path, monkeypatch):
    root = tmp_path / 'uploads'
    root.mkdir()
    reports = root / 'reports'
    reports.mkdir()
    outside = tmp_path / 'secret.xlsx'
    outside.write_text('private')
    (reports / 'link.xlsx').symlink_to(outside)
    monkeypatch.setattr('app.core.config.settings.UPLOAD_DIR', str(root))
    assert resolve_stored_file('../secret.xlsx', 'reports') is None
    assert resolve_stored_file(str(outside), 'reports') is None
    assert resolve_stored_file('reports/link.xlsx', 'reports') is None
    assert resolve_stored_file('reports/link.xlsx') is None
    assert resolve_stored_file('reports/missing.xlsx', 'reports') is None


def test_storage_resolves_legacy_paths_inside_the_allowed_directory(tmp_path, monkeypatch):
    directory = tmp_path / 'firmware'
    directory.mkdir()
    binary = directory / 'device.bin'
    binary.write_bytes(b'firmware')
    monkeypatch.setattr('app.core.config.settings.UPLOAD_DIR', str(tmp_path))
    assert resolve_stored_file('C:\\old\\uploads\\firmware\\device.bin', 'firmware') == binary
