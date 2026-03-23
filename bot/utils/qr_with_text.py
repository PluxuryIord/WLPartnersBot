from PIL import Image, ImageDraw, ImageFont
import qrcode
import textwrap
import os


def generate_qr_with_text(data, caption, output_path, width=600, qr_size=380, font_size=22, padding=30):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)

    font = None
    for fp in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', '/usr/share/fonts/truetype/freefont/FreeSans.ttf']:
        if os.path.exists(fp):
            font = ImageFont.truetype(fp, font_size)
            break
    if font is None:
        font = ImageFont.load_default()

    max_chars = max(10, (width - padding * 2) // (font_size // 2 + 2))
    lines = []
    for raw_line in caption.split('\n'):
        wrapped = textwrap.wrap(raw_line, width=max_chars) if raw_line.strip() else ['']
        lines.extend(wrapped)

    line_height = font_size + 6
    text_block_height = len(lines) * line_height
    total_height = padding + qr_size + 20 + text_block_height + padding
    canvas = Image.new('RGB', (width, total_height), 'white')
    draw = ImageDraw.Draw(canvas)

    qr_x = (width - qr_size) // 2
    canvas.paste(qr_img, (qr_x, padding))

    text_y = padding + qr_size + 20
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        tx = (width - tw) // 2
        draw.text((tx, text_y), line, fill='black', font=font)
        text_y += line_height

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    canvas.save(output_path, 'PNG')
    return output_path
