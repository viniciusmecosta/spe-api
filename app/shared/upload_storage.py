import asyncio
import io
import logging
import os
import tempfile
import uuid
import warnings
import zipfile
import zlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile
from PIL import Image

from app.core.config import settings
from app.core.exceptions import DomainException

logger = logging.getLogger(__name__)


class UploadCategory(StrEnum):
    LOGO = 'logo'
    ATTACHMENT = 'attachment'
    FIRMWARE = 'firmware'
    LEGACY_REPORT = 'legacy_report'


@dataclass(frozen=True)
class UploadPolicy:
    directory: str
    extensions: frozenset[str]
    limit_setting: str


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    relative_path: str
    size: int
    content_type: str


JPEG_EXTENSION = '.jpeg'
XLSX_EXTENSION = '.xlsx'
DOCX_EXTENSION = '.docx'


_POLICIES = {
    UploadCategory.LOGO: UploadPolicy('public', frozenset({'.png', '.jpg', JPEG_EXTENSION}), 'UPLOAD_LOGO_MAX_BYTES'),
    UploadCategory.ATTACHMENT: UploadPolicy('', frozenset({'.pdf', '.png', '.jpg', JPEG_EXTENSION}),
                                           'UPLOAD_ATTACHMENT_MAX_BYTES'),
    UploadCategory.FIRMWARE: UploadPolicy('firmware', frozenset({'.bin'}), 'UPLOAD_FIRMWARE_MAX_BYTES'),
    UploadCategory.LEGACY_REPORT: UploadPolicy('reports/legacy',
                                              frozenset({'.pdf', '.xls', XLSX_EXTENSION, '.csv', '.doc', DOCX_EXTENSION}),
                                              'UPLOAD_LEGACY_REPORT_MAX_BYTES'),
}
_CONTENT_TYPES = {
    '.png': 'image/png', '.jpg': 'image/jpeg', JPEG_EXTENSION: 'image/jpeg', '.pdf': 'application/pdf',
    '.bin': 'application/octet-stream', '.csv': 'text/csv', '.xls': 'application/vnd.ms-excel',
    '.doc': 'application/msword',
    XLSX_EXTENSION: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    DOCX_EXTENSION: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
_OLE_HEADER = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


class UploadStorage:
    def _extension(self, filename: str, category: UploadCategory) -> str:
        extension = Path(filename).suffix.lower()
        if extension not in _POLICIES[category].extensions:
            raise DomainException('Formato de arquivo não permitido para este envio.')
        return extension

    def _copy_bounded(self, source: BinaryIO, destination: BinaryIO, limit: int) -> int:
        size = 0
        while chunk := source.read(min(65536, limit - size + 1)):
            size += len(chunk)
            if size > limit:
                raise DomainException(f'O arquivo excede o limite de {limit} bytes.', status_code=413)
            destination.write(chunk)
        if not size:
            raise DomainException('O arquivo enviado está vazio.')
        return size

    def _validate_image(self, path: Path, extension: str) -> None:
        expected_format = 'PNG' if extension == '.png' else 'JPEG'
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    width, height = image.size
                    if image.format != expected_format:
                        raise ValueError('Formato de imagem incompatível.')
                    if max(width, height) > settings.UPLOAD_LOGO_MAX_DIMENSION:
                        raise ValueError('Dimensões de imagem excedidas.')
                    if width * height > settings.UPLOAD_LOGO_MAX_PIXELS:
                        raise ValueError('Quantidade de pixels excedida.')
                    image.verify()
                with Image.open(path) as image:
                    image.load()
        except (OSError, ValueError, SyntaxError,
                Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise DomainException('A imagem está inválida, corrompida ou excede as dimensões permitidas.') from exc

    def _validate_office_archive(self, path: Path, extension: str) -> None:
        expected_member = 'xl/workbook.xml' if extension == XLSX_EXTENSION else 'word/document.xml'
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
                    raise ValueError('Documento compactado excede o limite permitido.')
                names = set(archive.namelist())
                if '[Content_Types].xml' not in names or expected_member not in names:
                    raise ValueError('Estrutura do documento inválida.')
                if archive.testzip() is not None:
                    raise ValueError('Documento corrompido.')
        except (zipfile.BadZipFile, RuntimeError, OSError, ValueError, EOFError, zlib.error) as exc:
            raise DomainException('O documento Office está inválido ou corrompido.') from exc

    def _validate_document(self, path: Path, extension: str) -> None:
        with path.open('rb') as source:
            header = source.read(16)
            if extension == '.pdf' and not header.startswith(b'%PDF-'):
                raise DomainException('O conteúdo do arquivo não corresponde ao formato PDF.')
            if extension in {'.doc', '.xls'} and not header.startswith(_OLE_HEADER):
                raise DomainException('O conteúdo do arquivo não corresponde ao formato Office informado.')
            if extension == '.csv':
                while chunk := source.read(65536):
                    if b'\x00' in chunk:
                        raise DomainException('O conteúdo do arquivo não corresponde ao formato CSV.')
                if b'\x00' in header:
                    raise DomainException('O conteúdo do arquivo não corresponde ao formato CSV.')
        if extension in {XLSX_EXTENSION, DOCX_EXTENSION}:
            self._validate_office_archive(path, extension)

    def _validate_content(self, path: Path, extension: str, category: UploadCategory) -> None:
        if extension in {'.png', '.jpg', JPEG_EXTENSION}:
            self._validate_image(path, extension)
        elif category != UploadCategory.FIRMWARE:
            self._validate_document(path, extension)

    def _save(self, source: BinaryIO, original_filename: str, category: UploadCategory,
              filename: str | None) -> StoredUpload:
        extension = self._extension(original_filename, category)
        policy = _POLICIES[category]
        upload_root = Path(settings.UPLOAD_DIR).resolve()
        directory = (upload_root / policy.directory).resolve()
        if not directory.is_relative_to(upload_root):
            raise DomainException('Diretório de armazenamento inválido.')
        directory.mkdir(parents=True, exist_ok=True)
        final_name = filename or f'{uuid.uuid4().hex}{extension}'
        if (Path(final_name).name != final_name or Path(final_name).suffix.lower() != extension
                or "\\" in final_name or ":" in final_name):
            raise DomainException('Nome de arquivo inválido.')
        destination = directory / final_name
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.upload_', delete=False) as temporary:
                temporary_path = Path(temporary.name)
                source.seek(0)
                size = self._copy_bounded(source, temporary, getattr(settings, policy.limit_setting))
            self._validate_content(temporary_path, extension, category)
            os.replace(temporary_path, destination)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return StoredUpload(destination, destination.relative_to(upload_root).as_posix(), size,
                            _CONTENT_TYPES[extension])

    async def _store(self, source: BinaryIO, original_filename: str, category: UploadCategory,
                     filename: str | None) -> StoredUpload:
        worker = asyncio.create_task(asyncio.to_thread(self._save, source, original_filename, category, filename))
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            try:
                stored = await worker
            except Exception:
                logger.exception('Falha ao interromper o armazenamento de upload.')
            else:
                await self.remove(stored)
            raise

    async def save(self, file: UploadFile, category: UploadCategory, filename: str | None = None) -> StoredUpload:
        return await self._store(file.file, file.filename or '', category, filename)

    async def save_bytes(self, content: bytes, original_filename: str, category: UploadCategory,
                         filename: str | None = None) -> StoredUpload:
        return await self._store(io.BytesIO(content), original_filename, category, filename)

    async def remove(self, upload: StoredUpload) -> None:
        await self.remove_path(upload.path)

    async def remove_path(self, path: Path) -> None:
        root = Path(settings.UPLOAD_DIR).resolve()
        if not path.resolve().is_relative_to(root):
            return
        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError:
            logger.exception('Não foi possível remover arquivo de upload: %s', path.name)


upload_storage = UploadStorage()
