import asyncio
import io
import logging
import re

import qrcode
from escpos.printer import Network, File
from reportlab.lib.pagesizes import mm
from reportlab.pdfgen import canvas

from app.domain.models.printer import Printer

logger = logging.getLogger(__name__)


class ReceiptService:
    @staticmethod
    def _get_escpos_printer(printer_config: Printer):
        address = printer_config.address.strip()
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", address):
            return Network(address)
        return File(address)

    @staticmethod
    def _print_escpos_receipt(printer_config: Printer, data: dict):
        try:
            p = ReceiptService._get_escpos_printer(printer_config)
            try:
                p.set(align="center", bold=True)
                p.text("Comprovante de Registro de Ponto do Trabalhador\n\n")

                p.set(align="left", bold=False)
                p.text(f"Empresa: {data['company_name']}\n")
                p.text(f"CNPJ: {data['company_cnpj']}\n")
                p.text(f"Funcionario: {data['employee_name']}\n")
                p.text(f"CPF: {data['employee_cpf']}\n")
                p.text(f"PIS: {data['employee_pis']}\n")
                p.text(f"Data: {data['record_date']} | Hora: {data['record_time']}\n")
                p.text(f"Tipo: {data['record_type_str']} | NSR: {data['nsr']}\n")
                p.text(f"Local: {data['device_name']}\n\n")

                p.set(align="center")
                p.qr(data['short_id'], size=6)
                p.text(f"\n{data['short_id']}\n\n")

                p.cut()
            finally:
                p.close()
        except Exception as e:
            logger.exception(
                "Falha ao imprimir comprovante na impressora '%s' (%s): %s",
                printer_config.name,
                printer_config.address,
                e,
                exc_info=True,
            )

    @staticmethod
    async def print_receipt_async(printer_config: Printer, data: dict):
        return await asyncio.to_thread(ReceiptService._print_escpos_receipt, printer_config, data)

    @staticmethod
    def generate_pdf_receipt(data: dict) -> bytes:
        def val(k):
            v = data.get(k)
            if not v or v == "N/A" or str(v).strip() == "":
                return "N/A"
            return str(v)

        buffer = io.BytesIO()
        width = 80 * mm
        height = 31 * mm
        
        c = canvas.Canvas(buffer, pagesize=(width, height))
        
        c.setTitle(str(data['nsr']))
        c.setAuthor(str(val('company_name')))
        c.setSubject("Comprovante de Registro de Ponto")
        c.setCreator("Sistema de Ponto Eletrônico")
        
        c.setFont("Times-Bold", 7)
        c.drawCentredString(width / 2.0, height - 3 * mm, "Comprovante de Registro de Ponto")
        
        qr_size = 17 * mm
        qr_x = width - qr_size - 1 * mm
        qr_y = height - 7 * mm - qr_size
        
        qr = qrcode.QRCode(box_size=3, border=0)
        qr.add_data(val('short_id'))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        c.drawInlineImage(img, qr_x, qr_y, width=qr_size, height=qr_size)
        
        c.setFont("Times-Roman", 6)
        c.drawCentredString(qr_x + qr_size / 2.0, qr_y - 2 * mm, val('short_id'))
        
        c.setFont("Times-Roman", 7)
        text = c.beginText(1 * mm, height - 6.5 * mm)
        text.setLeading(7)
        text.textLine(f"Emp: {val('company_name')}")
        text.textLine(f"CNPJ: {val('company_cnpj')}")
        text.textLine(f"Func: {val('employee_name')}")
        text.textLine(f"CPF: {val('employee_cpf')}")
        text.textLine(f"PIS: {val('employee_pis')}")
        text.textLine(f"Data: {val('record_date')} | Hora: {val('record_time')}")
        text.textLine(f"Tipo: {val('record_type_str')} | NSR: {val('nsr')}")
        y_pos = text.getY()
        c.drawText(text)
        
        c.setFont("Times-Italic", 7)
        c.drawString(1 * mm, y_pos, f"Local: {val('device_name')}")
        
        c.showPage()
        c.save()
        
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        return pdf_bytes

receipt_service = ReceiptService()
