import pytest
from pydantic import ValidationError

from app.features.companies.company_schemas import CompanyUpdate
from app.features.devices.device_schemas import DeviceCredentialUpdate
from app.features.printers.printer_schemas import PrinterUpdate


@pytest.mark.parametrize('schema,field', [
    (CompanyUpdate, 'name'), (CompanyUpdate, 'cnpj'), (CompanyUpdate, 'address'),
    (CompanyUpdate, 'auto_print_receipt'),
    (PrinterUpdate, 'name'), (PrinterUpdate, 'address'), (PrinterUpdate, 'status'),
    (PrinterUpdate, 'paper_width'), (PrinterUpdate, 'company_id'),
    (DeviceCredentialUpdate, 'name'), (DeviceCredentialUpdate, 'is_active'),
])
def test_required_configuration_fields_reject_explicit_null(schema, field):
    payload = {field: None}
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


@pytest.mark.parametrize('schema', [CompanyUpdate, PrinterUpdate, DeviceCredentialUpdate])
def test_configuration_updates_accept_omitted_fields(schema):
    assert schema().model_dump(exclude_unset=True) == {}


def test_optional_company_fields_can_be_cleared():
    response = CompanyUpdate(phone=None, logo_path=None, default_printer_id=None)
    assert response.model_dump(exclude_unset=True) == {
        'phone': None, 'logo_path': None, 'default_printer_id': None,
    }
