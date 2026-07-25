import os
import sys
import pytest
from datetime import datetime
from io import BytesIO
from unittest.mock import MagicMock, patch
from openpyxl import Workbook
from fastapi import HTTPException

from app.services.excel_service import ExcelService
from app.domain.models.user import User
from app.domain.models.enums import UserRole

@pytest.fixture
def excel_service():
    return ExcelService()

@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 1
    user.name = "Test User"
    user.cpf = "12345678901"
    user.pis = "12345678901"
    user.phone = "11987654321"
    user.endereco = "Test Address"
    user.role = UserRole.EMPLOYEE
    return user

def test_setup_styles(excel_service):
    assert excel_service.font_regular.name == "Times New Roman"

def test_set_columns_width(excel_service):
    wb = Workbook()
    ws = wb.active
    excel_service._set_columns_width(ws)
    assert ws.column_dimensions["A"].width == 5

def test_format_cnpj(excel_service):
    assert excel_service._format_cnpj("") == "Não registrado"
    assert excel_service._format_cnpj("12345678901234") == "12.345.678/9012-34"
    assert excel_service._format_cnpj("123") == "123"

def test_format_phone(excel_service):
    assert excel_service._format_phone("") == "Não registrado"
    assert excel_service._format_phone("11987654321") == "(11) 98765-4321"
    assert excel_service._format_phone("1187654321") == "(11) 8765-4321"
    assert excel_service._format_phone("118765432") == "118765432"

def test_get_month_name(excel_service):
    assert excel_service._get_month_name(1) == "JANEIRO"
    assert excel_service._get_month_name(13) == ""

def test_time_str_to_fraction(excel_service):
    assert excel_service._time_str_to_fraction(None) == 0.0
    assert excel_service._time_str_to_fraction("10") == 0.0
    assert excel_service._time_str_to_fraction("invalid:time") == 0.0
    assert excel_service._time_str_to_fraction("aa:bb") == 0.0
    assert excel_service._time_str_to_fraction("10:30") == (10 + (30 / 60.0)) / 24.0
    assert excel_service._time_str_to_fraction(":") == 0.0

class MockDatetimeMay:
    class datetime:
        @classmethod
        def now(cls):
            class D:
                month = 5
                year = 2023
            return D()

def test_validate_employee_report_period(excel_service, mock_user, monkeypatch):
    excel_service._validate_employee_report_period(None, 5, 2023)
    
    manager_user = MagicMock(spec=User)
    manager_user.role = UserRole.MANAGER
    excel_service._validate_employee_report_period(manager_user, 1, 2020)
    
    monkeypatch.setitem(sys.modules, 'datetime', MockDatetimeMay)
    
    excel_service._validate_employee_report_period(mock_user, 5, 2023)
    excel_service._validate_employee_report_period(mock_user, 4, 2023)
    with pytest.raises(HTTPException):
        excel_service._validate_employee_report_period(mock_user, 3, 2023)

class MockDatetimeJan:
    class datetime:
        @classmethod
        def now(cls):
            class D:
                month = 1
                year = 2023
            return D()

def test_validate_employee_report_period_january(excel_service, mock_user, monkeypatch):
    monkeypatch.setitem(sys.modules, 'datetime', MockDatetimeJan)
    
    excel_service._validate_employee_report_period(mock_user, 1, 2023)
    excel_service._validate_employee_report_period(mock_user, 12, 2022)
    with pytest.raises(HTTPException):
        excel_service._validate_employee_report_period(mock_user, 11, 2022)

@patch.object(ExcelService, '_validate_employee_report_period')
@patch("app.services.excel_service.report_service")
@patch("app.services.excel_service.company_repository")
@patch("os.path.exists")
def test_generate_excel_report(mock_exists, mock_company_repo, mock_report_service, mock_validate, excel_service, db_session_mock, mock_user):
    mock_exists.return_value = True
    
    mock_company = MagicMock()
    mock_company.logo_path = "logo.png"
    mock_company.cnpj = "12345678901234"
    mock_company.phone = "11987654321"
    mock_company.address = "Address"
    mock_company.name = "Company"
    mock_company_repo.get_current.return_value = mock_company
    
    query_mock = MagicMock()
    query_mock.options.return_value = query_mock
    query_mock.all.return_value = [mock_user]
    db_session_mock.query.return_value = query_mock
    mock_report_service._apply_employee_filters.return_value = query_mock
    
    mock_report = MagicMock()
    mock_report.summary.total_worked_minutes = 100
    mock_report.summary.user_name = "Test User"
    mock_report.summary.days_worked = 1
    
    mock_day = MagicMock()
    mock_day.worked_time = "08:00"
    mock_day.unapproved_extra_time = "01:00"
    mock_day.is_holiday = False
    mock_day.is_weekend = False
    mock_day.status = "Normal"
    mock_day.punches = ["08:00", "12:00"]
    mock_day.date = datetime(2023, 5, 1)
    mock_day.day_name = "Segunda"
    
    mock_report.daily_details = [mock_day]
    mock_report_service.get_advanced_user_report.return_value = mock_report
    
    output = excel_service.generate_excel_report(db_session_mock, 5, 2023, [1], mock_user)
    assert isinstance(output, BytesIO)
    mock_validate.assert_called_once_with(mock_user, 5, 2023)

@patch("app.services.excel_service.report_service")
@patch("app.services.excel_service.company_repository")
def test_generate_excel_report_no_logo(mock_company_repo, mock_report_service, excel_service, db_session_mock, mock_user):
    mock_company = MagicMock()
    mock_company.logo_path = None
    mock_company.cnpj = "12345678901234"
    mock_company.phone = "11987654321"
    mock_company.address = "Address"
    mock_company.name = "Company"
    mock_company_repo.get_current.return_value = mock_company
    
    query_mock = MagicMock()
    query_mock.options.return_value = query_mock
    query_mock.all.return_value = [mock_user]
    db_session_mock.query.return_value = query_mock
    mock_report_service._apply_employee_filters.return_value = query_mock
    
    mock_report = MagicMock()
    mock_report.summary.total_worked_minutes = 100
    mock_report.summary.user_name = "Test User"
    mock_report.summary.days_worked = 1
    mock_day = MagicMock()
    mock_day.worked_time = "08:00"
    mock_day.unapproved_extra_time = None
    mock_day.is_holiday = True
    mock_day.holiday_name = "Dia do Trabalho"
    mock_day.is_weekend = False
    mock_day.status = "Feriado"
    mock_day.punches = []
    mock_day.date = datetime(2023, 5, 1)
    mock_day.day_name = "Segunda"
    mock_report.daily_details = [mock_day]
    mock_report_service.get_advanced_user_report.return_value = mock_report
    
    output = excel_service.generate_excel_report(db_session_mock, 5, 2023, [1])
    assert isinstance(output, BytesIO)

def test_apply_key_value(excel_service):
    wb = Workbook()
    ws = wb.active
    excel_service._apply_key_value(ws, 1, 1, "Key", 2, "Value", 2, borders=True)
    assert ws.cell(row=1, column=1).value == "Key"
    assert ws.cell(row=1, column=3).value == "Value"
    excel_service._apply_key_value(ws, 2, 1, "Key", 2, "Value", 2, borders=False)

@patch("app.services.excel_service.OpenpyxlImage")
def test_insert_header(mock_image, excel_service):
    wb = Workbook()
    ws = wb.active
    mock_company = MagicMock()
    mock_company.cnpj = "12345678901234"
    mock_company.phone = "11987654321"
    mock_company.address = "Address"
    excel_service._insert_header(ws, mock_company, "logo.png")
    assert ws.max_row > 1

@patch("app.services.excel_service.OpenpyxlImage")
def test_insert_header_no_company(mock_image, excel_service):
    wb = Workbook()
    ws = wb.active
    excel_service._insert_header(ws, None, None)
    assert ws.max_row > 1

@patch("app.services.excel_service.OpenpyxlImage")
def test_insert_header_image_error(mock_image, excel_service):
    mock_image.side_effect = ValueError("Invalid image")
    wb = Workbook()
    ws = wb.active
    mock_company = MagicMock()
    mock_company.cnpj = "12345678901234"
    mock_company.phone = "11987654321"
    mock_company.address = "Address"
    excel_service._insert_header(ws, mock_company, "logo.png")
    
    mock_image.side_effect = OSError("No file")
    excel_service._insert_header(ws, mock_company, "logo.png")

def test_append_notes(excel_service):
    wb = Workbook()
    ws = wb.active
    excel_service._append_notes(ws)
    assert ws.max_row >= 4

def test_merge_for_table(excel_service):
    wb = Workbook()
    ws = wb.active
    excel_service._merge_for_table(ws, 1, [2, 2], ["Text1", "Text2"], excel_service.font_regular, excel_service.align_center, fill=excel_service.fill_holiday, borders=True)
    excel_service._merge_for_table(ws, 2, [1], ["Text"], None, None, fill=None, borders=False)

def test_build_day_row(excel_service):
    wb = Workbook()
    ws = wb.active
    mock_day = MagicMock()
    mock_day.worked_time = "08:00"
    mock_day.unapproved_extra_time = "01:00"
    mock_day.is_holiday = False
    mock_day.is_weekend = True
    mock_day.status = "Falta"
    mock_day.punches = ["08:00", "12:00"]
    mock_day.date = datetime(2023, 5, 1)
    mock_day.day_name = "Sábado"
    
    excel_service._build_day_row(ws, mock_day, [1, 1, 1, 1, 1, 1, 1])
    
    mock_day.is_holiday = True
    mock_day.is_weekend = False
    mock_day.status = "Atestado"
    mock_day.punches = ["08:00"]
    mock_day.holiday_name = None
    excel_service._build_day_row(ws, mock_day, [1, 1, 1, 1, 1, 1, 1])

    mock_day.status = "Abonado"
    excel_service._build_day_row(ws, mock_day, [1, 1, 1, 1, 1, 1, 1])
    
    mock_day.is_holiday = True
    mock_day.punches = []
    mock_day.status = "Feriado"
    excel_service._build_day_row(ws, mock_day, [1, 1, 1, 1, 1, 1, 1])

def test_build_employee_sheet_no_phone_endereco(excel_service):
    wb = Workbook()
    mock_user = MagicMock(spec=User)
    mock_user.name = "Test User"
    mock_user.cpf = None
    mock_user.pis = None
    mock_user.phone = None
    mock_user.endereco = None
    
    mock_report = MagicMock()
    mock_report.daily_details = []
    
    excel_service._build_employee_sheet(wb, mock_user, mock_report, 5, 2023, None, None)
    assert "Tes" in wb.sheetnames[-1]

def test_build_summary_sheet(excel_service):
    wb = Workbook()
    mock_user = MagicMock(spec=User)
    mock_user.name = "Test User"
    
    mock_report = MagicMock()
    mock_report.summary.user_name = "Test User"
    mock_report.summary.days_worked = 1
    mock_report.summary.total_worked_minutes = 480
    
    mock_day = MagicMock()
    mock_day.worked_time = "08:00"
    mock_day.unapproved_extra_time = "01:00"
    mock_report.daily_details = [mock_day]
    
    excel_service._build_summary_sheet(wb, 5, 2023, [(mock_user, mock_report)], None, None)
    assert "Resumo" in wb.sheetnames

def test_build_summary_sheet_bruto_less_extra(excel_service):
    wb = Workbook()
    mock_user = MagicMock(spec=User)
    mock_user.name = "Test User"
    
    mock_report = MagicMock()
    mock_report.summary.user_name = "Test User"
    mock_report.summary.days_worked = 1
    mock_report.summary.total_worked_minutes = 480
    
    mock_day = MagicMock()
    mock_day.worked_time = "01:00"
    mock_day.unapproved_extra_time = "02:00"
    mock_report.daily_details = [mock_day]
    
    excel_service._build_summary_sheet(wb, 5, 2023, [(mock_user, mock_report)], None, None)
    assert "Resumo" in wb.sheetnames
