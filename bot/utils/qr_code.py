from typing import Tuple, Optional
from PIL import Image, ImageDraw
import qrcode

async def generate_qr_on_template(
    template_path: str,
    qr_data: str,
    output_path: str,
    qr_size: int,
    qr_position: Optional[Tuple[int, int]] = None,
    qr_color: str = "black",
    corner_radius: int = 40  # Радиус скругления углов QR
):
    print(qr_data)

    # Генерация QR-кода
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color=qr_color,
        back_color="transparent"
    ).convert("RGBA")

    qr_img = qr_img.resize((qr_size, qr_size), resample=Image.NEAREST)

    # Создание маски со скруглёнными углами
    mask = Image.new("L", (qr_size, qr_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, qr_size, qr_size), radius=corner_radius, fill=255)

    # Применяем маску к QR
    rounded_qr = Image.new("RGBA", (qr_size, qr_size))
    rounded_qr.paste(qr_img, (0, 0), mask=mask)

    # Загрузка шаблона
    template = Image.open(template_path).convert("RGBA")
    template_width, template_height = template.size

    # Центрирование по шаблону, если позиция не указана
    if qr_position is None:
        x = (template_width - qr_size) // 2
        y = (template_height - qr_size) // 2
        qr_position = (x, y)

    # Вставка QR на шаблон
    template.paste(rounded_qr, qr_position, rounded_qr)
    template.save(output_path)
