import asyncio
import io
import logging
import re

import qrcode
from escpos.printer import File, Network
from reportlab.lib.pagesizes import mm
from reportlab.pdfgen import canvas

from app.features.printers.printer_models import Printer

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
                p.text("COMPROVANTE DE REGISTRO DE PONTO DO TRABALHADOR\n\n")

                p.set(align="left", bold=False)
                p.text(f"EMPRESA: {data['company_name']}\n".upper())
                p.text(f"ENDEREÇO: {data.get('company_address', 'N/A')}\n".upper())
                p.text(f"CNPJ: {data['company_cnpj']}\n".upper())
                p.text(f"NOME: {data['employee_name']}\n".upper())
                p.text(f"CPF: {data['employee_cpf']} | PIS: {data['employee_pis']}\n".upper())
                p.text(f"DATA: {data['record_date']} | HORA: {data['record_time']}\n".upper())
                p.text(f"TIPO: {data['record_type_str']} | NSR: {data['nsr']}\n".upper())
                p.text(f"LOCAL: {data['device_name']}\n\n".upper())

                p.set(align="center")
                p.qr(str(data['short_id']).upper(), size=6)
                p.text(f"\n{str(data['short_id']).upper()}\n\n")

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
            return str(v).upper()

        buffer = io.BytesIO()
        width = 80 * mm
        height = 24 * mm

        c = canvas.Canvas(buffer, pagesize=(width, height))

        c.setTitle(str(data['nsr']))
        c.setAuthor(str(val('company_name')))
        c.setSubject("COMPROVANTE DE REGISTRO DE PONTO DO TRABALHADOR")
        c.setCreator("SISTEMA DE PONTO ELETRÔNICO")

        c.setFont("Courier-Bold", 6.5)
        c.drawCentredString(width / 2.0, height - 2.5 * mm, "COMPROVANTE DE REGISTRO DE PONTO DO TRABALHADOR")

        qr_size = 14 * mm
        qr_x = width - qr_size - 1 * mm
        qr_y = height - 5 * mm - qr_size

        qr = qrcode.QRCode(box_size=3, border=0)
        qr.add_data(val('short_id'))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        c.drawInlineImage(img, qr_x, qr_y, width=qr_size, height=qr_size)

        c.setFont("Courier-Bold", 6)
        c.drawCentredString(qr_x + qr_size / 2.0, qr_y - 2 * mm, val('short_id'))

        c.setFont("Courier", 6)
        text = c.beginText(1 * mm, height - 5 * mm)
        text.setLeading(5.8)
        text.textLine(f"EMP: {val('company_name')}")
        text.textLine(f"END: {val('company_address')}")
        text.textLine(f"CNPJ: {val('company_cnpj')}")
        text.textLine(f"NOME: {val('employee_name')}")
        text.textLine(f"CPF: {val('employee_cpf')} | PIS: {val('employee_pis')}")
        text.textLine(f"DATA: {val('record_date')} | HORA: {val('record_time')}")
        text.textLine(f"TIPO: {val('record_type_str')} | NSR: {val('nsr')}")
        y_pos = text.getY()
        c.drawText(text)

        c.setFont("Courier", 6)
        c.drawString(1 * mm, y_pos, f"LOCAL: {val('device_name')}")

        c.showPage()
        c.save()

        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes


receipt_service = ReceiptService()
