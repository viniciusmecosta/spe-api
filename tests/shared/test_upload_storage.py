import io
import zipfile

import pytest
from fastapi import UploadFile
from PIL import Image

from app.core.config import settings
from app.core.exceptions import DomainException
from app.shared.upload_storage import UploadCategory, upload_storage


def image_content(size=(4, 4), image_format='PNG'):
    buffer = io.BytesIO()
    Image.new('RGB', size, 'blue').save(buffer, format=image_format)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def upload_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, 'UPLOAD_DIR', str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
@pytest.mark.parametrize(('category', 'filename', 'content', 'setting'), [
    (UploadCategory.LOGO, 'logo.png', image_content(), 'UPLOAD_LOGO_MAX_BYTES'),
    (UploadCategory.ATTACHMENT, 'attachment.pdf', b'%PDF-1.4\nbody', 'UPLOAD_ATTACHMENT_MAX_BYTES'),
    (UploadCategory.FIRMWARE, 'firmware.bin', b'firmware bytes', 'UPLOAD_FIRMWARE_MAX_BYTES'),
    (UploadCategory.LEGACY_REPORT, 'report.csv', b'name,hours\nAlice,8', 'UPLOAD_LEGACY_REPORT_MAX_BYTES'),
])
async def test_category_limits_reject_before_persisting(category, filename, content, setting, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, setting, len(content) - 1)
    file = UploadFile(filename=filename, file=io.BytesIO(content))
    with pytest.raises(DomainException) as error:
        await upload_storage.save(file, category)
    assert error.value.status_code == 413
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]


@pytest.mark.asyncio
@pytest.mark.parametrize(('filename', 'content'), [
    ('logo.png', b'this is not an image'),
    ('logo.png', image_content(image_format='JPEG')),
    ('logo.jpg', image_content()),
    ('logo.png', image_content()[:32]),
])
async def test_logo_rejects_corruption_and_content_mismatch(filename, content, tmp_path):
    with pytest.raises(DomainException, match='imagem'):
        await upload_storage.save_bytes(content, filename, UploadCategory.LOGO)
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]


@pytest.mark.asyncio
@pytest.mark.parametrize(('setting', 'limit'), [('UPLOAD_LOGO_MAX_DIMENSION', 3), ('UPLOAD_LOGO_MAX_PIXELS', 15)])
async def test_image_dimension_limits(setting, limit, monkeypatch):
    monkeypatch.setattr(settings, setting, limit)
    content = image_content()
    with pytest.raises(DomainException, match='dimensões'):
        await upload_storage.save_bytes(content, 'logo.png', UploadCategory.LOGO)


@pytest.mark.asyncio
async def test_store_valid_logo_and_remove(tmp_path):
    content = image_content()
    stored = await upload_storage.save_bytes(content, 'company.PNG', UploadCategory.LOGO)
    assert stored.path.parent == tmp_path / 'public'
    assert stored.path.read_bytes() == content
    assert stored.size == len(content)
    assert stored.content_type == 'image/png'
    assert stored.relative_path == f'public/{stored.path.name}'
    await upload_storage.remove(stored)
    assert not stored.path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('category', list(UploadCategory))
async def test_empty_upload_is_rejected(category):
    filename = {'logo': 'a.png', 'attachment': 'a.pdf', 'firmware': 'a.bin', 'legacy_report': 'a.csv'}[category]
    with pytest.raises(DomainException, match='vazio'):
        await upload_storage.save_bytes(b'', filename, category)


@pytest.mark.asyncio
@pytest.mark.parametrize(('filename', 'content'), [
    ('report.pdf', b'text instead of PDF'), ('report.xls', b'not an office document'),
    ('report.doc', b'not an office document'), ('report.xlsx', b'PK fake archive'),
    ('report.docx', b'PK fake archive'), ('report.csv', b'name,\x00binary'),
])
async def test_invalid_legacy_document_rejected(filename, content, tmp_path):
    with pytest.raises(DomainException):
        await upload_storage.save_bytes(content, filename, UploadCategory.LEGACY_REPORT)
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]


@pytest.mark.asyncio
@pytest.mark.parametrize(('extension', 'member'), [('.xlsx', 'xl/workbook.xml'), ('.docx', 'word/document.xml')])
async def test_office_archive_requires_matching_structure(extension, member):
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr(member, '<document/>')
    stored = await upload_storage.save_bytes(content.getvalue(), f'report{extension}', UploadCategory.LEGACY_REPORT)
    assert stored.path.read_bytes() == content.getvalue()
    wrong = '.docx' if extension == '.xlsx' else '.xlsx'
    invalid_content = content.getvalue()
    with pytest.raises(DomainException):
        await upload_storage.save_bytes(invalid_content, f'report{wrong}', UploadCategory.LEGACY_REPORT)


@pytest.mark.asyncio
async def test_failed_finalize_removes_temporary_file(monkeypatch, tmp_path):
    def fail_replace(*args):
        raise OSError('injected disk failure')
    monkeypatch.setattr('app.shared.upload_storage.os.replace', fail_replace)
    with pytest.raises(OSError, match='injected'):
        await upload_storage.save_bytes(b'firmware', 'firmware.bin', UploadCategory.FIRMWARE)
    assert list((tmp_path / 'firmware').iterdir()) == []


@pytest.mark.asyncio
async def test_symlink_directory_cannot_escape_upload_root(tmp_path):
    external = tmp_path.parent / f'{tmp_path.name}-external'
    external.mkdir()
    (tmp_path / 'firmware').symlink_to(external, target_is_directory=True)
    with pytest.raises(DomainException, match='Diretório'):
        await upload_storage.save_bytes(b'firmware', 'firmware.bin', UploadCategory.FIRMWARE)
    assert list(external.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('filename', ['../evil.bin', '/evil.bin', 'wrong.pdf', r'C:\evil.bin'])
async def test_generated_filename_cannot_change_path_or_extension(filename):
    with pytest.raises(DomainException, match='Nome'):
        await upload_storage.save_bytes(b'firmware', 'firmware.bin', UploadCategory.FIRMWARE, filename)


@pytest.mark.asyncio
async def test_removal_preserves_files_outside_upload_root(tmp_path):
    external = tmp_path.parent / f'{tmp_path.name}-file'
    external.write_bytes(b'preserve')
    await upload_storage.remove_path(external)
    assert external.read_bytes() == b'preserve'
    external.unlink()


@pytest.mark.asyncio
async def test_upload_storage_validation_and_cancellation_branches(tmp_path):
    import asyncio
    from unittest.mock import MagicMock, patch
    from app.shared.upload_storage import StoredUpload

    with pytest.raises(DomainException, match="Formato de arquivo"):
        upload_storage._extension("evil.exe", UploadCategory.LOGO)

    huge_zip = tmp_path / "huge.xlsx"
    with zipfile.ZipFile(huge_zip, "w") as zf:
        zf.writestr("[Content_Types].xml", "ok")
        zf.writestr("xl/workbook.xml", "ok")
    fake_info = MagicMock()
    fake_info.file_size = 101 * 1024 * 1024
    with patch("zipfile.ZipFile.infolist", return_value=[fake_info]):
        with pytest.raises(DomainException, match="inválido ou corrompido"):
            upload_storage._validate_office_archive(huge_zip, ".xlsx")

    with patch("zipfile.ZipFile.testzip", return_value="xl/workbook.xml"):
        with pytest.raises(DomainException, match="inválido ou corrompido"):
            upload_storage._validate_office_archive(huge_zip, ".xlsx")

    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_bytes(b"a,b,c,d,e,f,g,h\n" + b"x" * 20 + b"\x00")
    with pytest.raises(DomainException, match="formato CSV"):
        upload_storage._validate_document(bad_csv, ".csv")

    stored_file = tmp_path / "public" / "test.png"
    stored_file.parent.mkdir(parents=True, exist_ok=True)
    stored_file.write_bytes(b"data")
    stored_upload = StoredUpload(stored_file, "public/test.png", 4, "image/png")

    async def fake_to_thread_success(*args, **kwargs):
        await asyncio.sleep(0.05)
        return stored_upload

    with patch("app.shared.upload_storage.asyncio.to_thread", side_effect=fake_to_thread_success):
        task = asyncio.create_task(upload_storage._store(io.BytesIO(b"data"), "test.png", UploadCategory.LOGO, "test.png"))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async def fake_to_thread_error(*args, **kwargs):
        await asyncio.sleep(0.05)
        raise RuntimeError("save failed")

    with patch("app.shared.upload_storage.asyncio.to_thread", side_effect=fake_to_thread_error):
        task2 = asyncio.create_task(upload_storage._store(io.BytesIO(b"data"), "test.png", UploadCategory.LOGO, "test.png"))
        await asyncio.sleep(0.01)
        task2.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task2

    with patch("app.shared.upload_storage.asyncio.to_thread", side_effect=OSError("unlink error")):
        await upload_storage.remove_path(stored_file)
