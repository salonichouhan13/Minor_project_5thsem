"""Small helpers: QR image generation and LAN address detection."""
import io
import socket
import qrcode


def make_qr_png(text: str) -> io.BytesIO:
    qr = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#601D49", back_color="#FFEBB8")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def lan_ip() -> str:
    """Phones can't open the laptop's 'localhost', so QR links use the LAN IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def base_url(req) -> str:
    host, _, port = req.host.partition(":")
    if host in ("localhost", "127.0.0.1", "::1"):
        host = lan_ip()
    return f"{req.scheme}://{host}" + (f":{port}" if port else "")
