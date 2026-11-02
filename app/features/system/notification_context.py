import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.config import settings
from app.features.companies.company_models import Company
from app.utils.formatters import mask_cnpj


def company_identity(context: dict) -> tuple[str, str]:
    name = ' '.join(str(context.get('company') or context.get('project') or settings.PROJECT_NAME).split())
    cnpj = ' '.join(str(context.get('cnpj') or '').split())
    return name, mask_cnpj(cnpj)


def format_company_phone(value: str) -> str:
    if any(character.isalpha() for character in value):
        return value
    digits = re.sub(r'\D', '', value)
    if len(digits) in (12, 13) and digits.startswith('55'):
        return f'+55 {format_company_phone(digits[2:])}'
    if len(digits) == 11:
        return f'({digits[:2]}) {digits[2:7]}-{digits[7:]}'
    if len(digits) == 10:
        return f'({digits[:2]}) {digits[2:6]}-{digits[6:]}'
    return value


def logo_file(logo_path: str | None) -> Path | None:
    if not logo_path or Path(logo_path).name != logo_path:
        return None
    root = Path(settings.UPLOAD_DIR).resolve()
    for candidate in (root / 'public' / logo_path, root / logo_path):
        if candidate.is_file() and candidate.resolve().is_relative_to(root):
            return candidate
    return None


def base_context() -> dict[str, str]:
    return {
        'project': settings.PROJECT_NAME,
        'version': settings.APP_VERSION,
        'environment': settings.ENVIRONMENT,
        'timezone': settings.TIMEZONE,
        'generated_at': datetime.now(ZoneInfo(settings.TIMEZONE)).strftime('%d/%m/%Y %H:%M'),
    }


async def company_context(session) -> dict[str, str]:
    context = base_context()
    company = await session.scalar(select(Company).order_by(Company.id).limit(1))
    if company:
        context.update(company=company.name, cnpj=company.cnpj, address=company.address,
                       phone=company.phone or '', logo_path=company.logo_path or '')
    return context
