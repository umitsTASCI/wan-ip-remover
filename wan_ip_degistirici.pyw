# -*- coding: utf-8 -*-
"""
WAN IP Değiştirici — TP-Link TD-W9970
=====================================

Modemin yönetim arayüzüne giriş yapar, seçilen PPPoE WAN bağlantısını
keser ve yeniden bağlar. Böylece ISS'den yeni bir genel IP alınması
amaçlanır. İşlem istenen aralıkla (varsayılan 2 dakika) otomatik tekrarlanır.

Yalnızca Python standart kütüphanesi kullanılır (tkinter dahil).
Harici paket gerekmez.

Çalıştırma:
    pythonw wan_ip_degistirici.pyw

Test:
    python wan_ip_degistirici.pyw --selftest
"""

from __future__ import annotations

import base64
import ctypes
import http.cookiejar
import json
import os
import queue
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

APP_NAME = "WAN IP Değiştirici"
APP_VERSION = "1.0"
APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
LOG_FILE = APP_DIR / "wan_ip_degistirici.log"
MAX_LOG_BYTES = 1_000_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

LOGIN_MARKERS = (
    "login.htm",
    "pc-login",
    "login-password",
    "loginerror",
    "login_error",
    'id="login',
    "id='login",
)


# ---------------------------------------------------------------------------
# Günlük (log) yardımcıları
# ---------------------------------------------------------------------------

def now_text() -> str:
    return time.strftime("%d.%m.%Y %H:%M:%S")


def append_file_log(line: str) -> None:
    """Günlük dosyasına yazar; dosya 1 MB'ı geçerse döndürür."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
            old = LOG_FILE.with_name(LOG_FILE.name + ".1")
            try:
                if old.exists():
                    old.unlink()
            except OSError:
                pass
            try:
                LOG_FILE.rename(old)
            except OSError:
                pass
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        # Günlük yazılamıyorsa program çalışmaya devam eder.
        pass


# ---------------------------------------------------------------------------
# Windows DPAPI ile şifre saklama
# ---------------------------------------------------------------------------

class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _make_blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    return blob, buf


def dpapi_protect(text: str) -> str | None:
    """Metni Windows DPAPI ile şifreler, base64 döndürür. Desteklenmiyorsa None."""
    if os.name != "nt":
        return None
    try:
        blob_in, keepalive = _make_blob(text.encode("utf-8"))
        blob_out = _DataBlob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            ctypes.c_wchar_p("WAN IP Degistirici"),
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None
        try:
            raw = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


def dpapi_unprotect(encoded: str) -> str | None:
    """DPAPI ile şifrelenmiş base64 metni çözer. Başarısızsa None."""
    if os.name != "nt" or not encoded:
        return None
    try:
        blob_in, keepalive = _make_blob(base64.b64decode(encoded))
        blob_out = _DataBlob()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        )
        if not ok:
            return None
        try:
            raw = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return raw.decode("utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    host: str = "192.168.1.1"
    username: str = "admin"
    target: str = "dsl_internet"
    interval_sec: int = 120
    disconnect_wait: int = 6
    connect_timeout: int = 75
    password_dpapi: str = ""
    password_plain: str = ""

    def password(self) -> str:
        if self.password_dpapi:
            value = dpapi_unprotect(self.password_dpapi)
            if value is not None:
                return value
        return self.password_plain

    def set_password(self, value: str) -> None:
        encrypted = dpapi_protect(value)
        if encrypted is not None:
            self.password_dpapi = encrypted
            self.password_plain = ""
        else:
            self.password_dpapi = ""
            self.password_plain = value

    def has_password(self) -> bool:
        return bool(self.password_dpapi or self.password_plain)


def load_settings() -> Settings:
    settings = Settings()
    if not CONFIG_FILE.exists():
        return settings
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if not isinstance(data, dict):
        return settings
    for name in ("host", "username", "target", "password_dpapi", "password_plain"):
        value = data.get(name)
        if isinstance(value, str):
            setattr(settings, name, value)
    for name in ("interval_sec", "disconnect_wait", "connect_timeout"):
        value = data.get(name)
        if isinstance(value, int):
            setattr(settings, name, value)
    settings.interval_sec = max(60, min(settings.interval_sec, 86_400))
    settings.disconnect_wait = max(0, min(settings.disconnect_wait, 300))
    settings.connect_timeout = max(15, min(settings.connect_timeout, 600))
    return settings


def save_settings(settings: Settings) -> None:
    CONFIG_FILE.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Küçük yardımcılar
# ---------------------------------------------------------------------------

def normalize_host(raw: str) -> str:
    host = (raw or "").strip()
    if not host:
        return ""
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0].strip()
    return host


def clean_ip(value: str | None) -> str:
    text = (value or "").strip()
    if not text or text == "0.0.0.0":
        return ""
    return text


def looks_like_login_page(text: str) -> bool:
    low = (text or "").lower()
    if "wan_ppp_conn" in low or "[error]0" in low:
        return False
    return any(marker in low for marker in LOGIN_MARKERS)


def parse_cgi_entries(text: str) -> list[dict]:
    """
    TP-Link CGI yanıtını kayıtlara ayırır.

    Örnek:
        [1,1,1,0,0,0]0
        name=dsl_internet
        connectionStatus=Connected
        externalIPAddress=88.1.2.3
        [error]0
    """
    entries: list[dict] = []
    current: dict | None = None
    for raw_line in (text or "").splitlines():
        line = raw_line.strip("\r\n")
        if not line:
            continue
        if line.startswith("["):
            match = re.match(r"^\[([^\]]+)\]", line)
            if not match:
                current = None
                continue
            stack = match.group(1).strip()
            if not re.fullmatch(r"\d+(?:,\d+)*", stack):
                current = None
                continue
            current = {"__stack": stack}
            entries.append(current)
            continue
        if current is not None and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                current[key] = value
    return entries


def choose_entry(entries: list[dict], target: str) -> dict | None:
    """
    Hedef ada tam eşleşen kaydı döndürür. Hedef boşsa bağlı olanı,
    o da yoksa ilk kaydı seçer. Hedef verilmiş ama bulunamadıysa None.
    """
    wanted = (target or "").strip()
    if wanted:
        for entry in entries:
            if entry.get("name") == wanted:
                return entry
        return None
    for entry in entries:
        if entry.get("connectionStatus") == "Connected":
            return entry
    return entries[0] if entries else None


def find_entry(entries: list[dict], name: str, stack: str) -> dict | None:
    for entry in entries:
        if entry.get("__stack") == stack:
            return entry
    for entry in entries:
        if name and entry.get("name") == name:
            return entry
    return None


# ---------------------------------------------------------------------------
# RSA (PKCS#1 v1.5) — TP-Link'in istemci tarafı şifrelemesi
# ---------------------------------------------------------------------------

def rsa_encrypt(message: bytes, n: int, e: int) -> str:
    """
    PKCS#1 v1.5 (type 2) dolgulu RSA şifrelemesi.
    TP-Link, sonucu küçük harfli ve modulus uzunluğunda hex bekler.
    """
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 11:
        raise ValueError("RSA mesajı çok uzun")
    padding_len = k - len(message) - 3
    padding = bytes(secrets.randbelow(255) + 1 for _ in range(padding_len))
    encoded = b"\x00\x02" + padding + b"\x00" + message
    number = int.from_bytes(encoded, "big")
    encrypted = pow(number, e, n)
    return encrypted.to_bytes(k, "big").hex()


# ---------------------------------------------------------------------------
# Router istemcisi
# ---------------------------------------------------------------------------

class RouterError(Exception):
    """Modemle iletişimde oluşan genel hata."""


class AuthError(RouterError):
    """Giriş başarısız (yanlış şifre, kilitli oturum vb.)."""


class RouterClient:
    """TP-Link TD-W9970 klasik web arayüzü istemcisi."""

    def __init__(self, host: str, username: str, password: str, timeout: int = 12):
        self.host = normalize_host(host)
        if not self.host:
            raise RouterError("Modem adresi boş olamaz.")
        self.base = f"http://{self.host}"
        self.username = username
        self.password = password
        self.timeout = timeout
        self.token: str | None = None
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )

    # -- alt seviye HTTP ----------------------------------------------------

    @staticmethod
    def _net_reason(reason) -> str:
        if isinstance(reason, ConnectionRefusedError):
            return "bağlantı reddedildi"
        if isinstance(reason, TimeoutError):
            return "zaman aşımı"
        text = str(reason or "")
        if "timed out" in text.lower():
            return "zaman aşımı"
        return text or "bilinmeyen ağ hatası"

    def _request(
        self,
        method: str,
        path: str,
        data: bytes | str | None = None,
        timeout: int | None = None,
        use_token: bool = True,
    ) -> tuple[int, str, object]:
        url = self.base + path
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Referer": self.base + "/",
            "Origin": self.base,
            "Connection": "close",
        }
        if data is not None:
            headers["Content-Type"] = "text/plain"
            if isinstance(data, str):
                data = data.encode("utf-8")
        if use_token and self.token:
            headers["TokenID"] = self.token

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read()
                status = response.status
                response_headers = response.headers
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            response_headers = exc.headers
        except urllib.error.URLError as exc:
            raise RouterError(
                f"Modeme bağlanılamadı ({self.base}): {self._net_reason(exc.reason)}. "
                "Modem açık mı ve bu bilgisayar aynı ağda mı?"
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise RouterError(
                f"Modeme bağlanılamadı ({self.base}): {self._net_reason(exc)}"
            ) from exc

        text = raw.decode("utf-8", "replace")
        return status, text, response_headers

    def _has_cookie(self, name: str) -> bool:
        return any(cookie.name == name for cookie in self._jar)

    @staticmethod
    def _extract_token(text: str) -> str | None:
        match = re.search(r'var\s+token\s*=\s*["\']([^"\']+)["\']', text or "")
        return match.group(1) if match else None

    # -- oturum -------------------------------------------------------------

    def _get_public_key(self) -> tuple[int, int]:
        last_error = ""
        path = f"/cgi/getParm?_={int(time.time() * 1000)}"
        for method in ("POST", "GET"):
            try:
                status, text, _ = self._request(
                    method, path, data=b"" if method == "POST" else None,
                    use_token=False,
                )
            except RouterError as exc:
                last_error = str(exc)
                continue
            if status == 200:
                nn_match = re.search(r'var\s+nn\s*=\s*"([0-9A-Fa-f]+)"', text)
                ee_match = re.search(r'var\s+ee\s*=\s*"([0-9A-Fa-f]+)"', text)
                if nn_match and ee_match:
                    return int(nn_match.group(1), 16), int(ee_match.group(1), 16)
            last_error = f"HTTP {status}"
        raise RouterError(
            "Modem RSA anahtarını vermedi (/cgi/getParm). "
            f"Adres doğru mu? {last_error}"
        )

    def login(self) -> None:
        n, e = self._get_public_key()
        user_hex = rsa_encrypt(self.username.encode("utf-8"), n, e)
        pass_hex = rsa_encrypt(
            base64.b64encode(self.password.encode("utf-8")), n, e
        )
        path = (
            f"/cgi/login?UserName={user_hex}&Passwd={pass_hex}"
            "&Action=1&LoginStatus=0"
        )

        status, text, _ = self._request("POST", path, data=b"", use_token=False)
        if status in (404, 405, 501):
            status, text, _ = self._request("GET", path, use_token=False)

        if status != 200:
            raise RouterError(
                f"Giriş isteği beklenmeyen yanıt verdi (HTTP {status})."
            )

        # TD-W9970 giriş yanıtı: başarıda "$.ret=0;", hatada "$.ret=71233;"
        ret_match = re.search(r"\$\.ret\s*=\s*(-?\d+)", text)
        if ret_match and ret_match.group(1) != "0":
            code = int(ret_match.group(1))
            details = ""
            times_match = re.search(r"currAuthTimes\s*=\s*(\d+)", text)
            forbid_match = re.search(r"currForbidTime\s*=\s*(\d+)", text)
            if times_match:
                details += f"\nModem hatalı deneme sayacı: {times_match.group(1)}"
            if forbid_match and int(forbid_match.group(1)) > 0:
                details += f"\nModem kilit süresi: {forbid_match.group(1)} sn"
            if code == 71233:
                reason = "Kullanıcı adı veya şifre hatalı."
            elif code == 71234:
                reason = "Modem giriş isteğini geçersiz buldu."
            else:
                reason = f"Modem girişi reddetti (hata kodu {code})."
            raise AuthError(
                f"Giriş başarısız: {reason}{details}\n\n"
                "Modemin web arayüzü başka bir tarayıcıda açık olabilir; "
                "kapatıp tekrar deneyin.\n"
                "DİKKAT: 5 hatalı denemeden sonra modem 10 dakika kilitlenir. "
                "Program güvenlik için durduruldu."
            )

        if not self._has_cookie("JSESSIONID"):
            raise AuthError(
                "Giriş başarısız: oturum çerezi oluşmadı. "
                "Kullanıcı adı/şifre hatalı olabilir veya modemin web arayüzü "
                "başka bir tarayıcıda açık olabilir.\n\n"
                "DİKKAT: 5 hatalı denemeden sonra modem 10 dakika kilitlenir. "
                "Program güvenlik için durduruldu."
            )

        token = self._extract_token(text)
        index_status, index_text, _ = self._request("GET", "/", use_token=False)
        if index_status == 200:
            token = token or self._extract_token(index_text)
            if not token and looks_like_login_page(index_text):
                raise AuthError(
                    "Giriş başarısız. Kullanıcı adı/şifre hatalı olabilir veya "
                    "modemin web arayüzü başka bir oturumda açık.\n\n"
                    "DİKKAT: 5 hatalı denemeden sonra modem 10 dakika kilitlenir. "
                    "Program güvenlik için durduruldu."
                )
        self.token = token

    def logout(self) -> None:
        try:
            self._request("GET", "/cgi/logout", timeout=5)
        except Exception:
            pass
        self.token = None
        try:
            self._jar.clear()
        except Exception:
            pass

    # -- CGI işlemleri ------------------------------------------------------

    def _cgi(self, act: int, body: str) -> str:
        status, text, _ = self._request("POST", f"/cgi?{act}", data=body)
        if status in (401, 403):
            raise AuthError(
                f"Oturum açılamadı (HTTP {status}). Modemin web arayüzü başka "
                "bir tarayıcıda açık olabilir; kapatıp tekrar deneyin."
            )
        if status != 200:
            raise RouterError(f"Modem isteği reddetti (HTTP {status}).")
        if looks_like_login_page(text):
            raise AuthError(
                "Oturum düşmüş görünüyor. Modemin web arayüzü başka bir "
                "tarayıcıda açık olabilir; kapatıp tekrar deneyin."
            )
        return text

    def list_wan(self) -> list[dict]:
        body = "[WAN_PPP_CONN#0,0,0,0,0,0#0,0,0,0,0,0]0,0\r\n"
        text = self._cgi(5, body)
        entries = parse_cgi_entries(text)
        if not entries:
            error_match = re.search(r"\[error\](\d+)", text)
            if error_match and error_match.group(1) != "0":
                raise RouterError(
                    "WAN listesi alınamadı "
                    f"(modem hata kodu {error_match.group(1)})."
                )
            raise RouterError(
                "Modem WAN listesi için boş yanıt verdi. "
                "Yazılım sürümü bu komutu desteklemiyor olabilir."
            )
        return entries

    def ppp_action(self, action: str, stack: str) -> None:
        body = f"[{action}#{stack}#0,0,0,0,0,0]0,0\r\n"
        text = self._cgi(7, body)
        error_match = re.search(r"\[error\](\d+)", text)
        if error_match is None:
            raise RouterError(
                f"Modem '{action}' komutuna beklenmeyen yanıt verdi: "
                f"{text.strip()[:120] or '(boş)'}"
            )
        if error_match.group(1) != "0":
            raise RouterError(
                f"Modem '{action}' komutunu reddetti "
                f"(hata kodu {error_match.group(1)})."
            )


# ---------------------------------------------------------------------------
# Arayüz
# ---------------------------------------------------------------------------

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = load_settings()
        self.queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.running = False
        self.busy = False
        self.stopping = False
        self.next_run: float | None = None
        self.auth_failed = False

        self._build_ui()
        self._load_settings_into_ui()
        self.root.report_callback_exception = self._tk_exception
        self.root.after(150, self._drain_queue)
        self.root.after(250, self._tick)

        self._log("info", f"{APP_NAME} v{APP_VERSION} hazır.")
        self._log(
            "dim",
            "İpucu: Modemin web arayüzünü aynı anda başka bir tarayıcıda "
            "açık bırakmayın; modem tek yönetici oturumu kabul eder.",
        )

    # -- kurulum ------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.title(f"{APP_NAME} — TP-Link TD-W9970")
        self.root.geometry("880x780")
        self.root.minsize(800, 700)

        style = ttk.Style()
        for theme in ("vista", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground="#6b7280")
        style.configure("Hint.TLabel", font=("Segoe UI", 8), foreground="#6b7280")
        style.configure("StatusOk.TLabel", font=("Segoe UI", 11, "bold"), foreground="#15803d")
        style.configure("StatusRun.TLabel", font=("Segoe UI", 11, "bold"), foreground="#1d4ed8")
        style.configure("StatusErr.TLabel", font=("Segoe UI", 11, "bold"), foreground="#b91c1c")
        style.configure("StatusIdle.TLabel", font=("Segoe UI", 11, "bold"), foreground="#4b5563")
        style.configure("Ip.TLabel", font=("Consolas", 11, "bold"))

        main = ttk.Frame(self.root, padding=14)
        main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(5, weight=1)

        # Başlık
        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="WAN IP Değiştirici", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="TP-Link TD-W9970 • PPPoE WAN bağlantısını keser, yeniden bağlar ve yeni IP'yi doğrular",
            style="Sub.TLabel",
        ).pack(anchor="w")

        # Bağlantı ayarları
        conn = ttk.LabelFrame(main, text=" Bağlantı Ayarları ", padding=(12, 8))
        conn.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        conn.columnconfigure(1, weight=1)
        conn.columnconfigure(3, weight=1)

        ttk.Label(conn, text="Modem adresi:").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=5)
        self.host_var = tk.StringVar()
        ttk.Entry(conn, textvariable=self.host_var).grid(
            row=0, column=1, sticky="ew", padx=(0, 18), pady=5
        )

        ttk.Label(conn, text="Kullanıcı adı:").grid(row=0, column=2, sticky="w", padx=(0, 6), pady=5)
        self.user_var = tk.StringVar()
        ttk.Entry(conn, textvariable=self.user_var).grid(
            row=0, column=3, sticky="ew", pady=5
        )

        ttk.Label(conn, text="Şifre:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=5)
        self.pass_var = tk.StringVar()
        self.pass_entry = ttk.Entry(conn, textvariable=self.pass_var, show="•")
        self.pass_entry.grid(row=1, column=1, sticky="ew", padx=(0, 18), pady=5)
        self.show_pass_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            conn, text="Göster", variable=self.show_pass_var, command=self._toggle_pass
        ).grid(row=1, column=2, sticky="w", padx=(0, 6), pady=5)
        ttk.Label(
            conn,
            text="Kayıtlıysa boş bırakabilirsiniz (Windows DPAPI ile saklanır)",
            style="Hint.TLabel",
        ).grid(row=1, column=3, sticky="w", pady=5)

        ttk.Label(conn, text="Hedef WAN:").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=5)
        self.target_var = tk.StringVar()
        self.target_combo = ttk.Combobox(
            conn, textvariable=self.target_var, values=["dsl_internet"], width=28
        )
        self.target_combo.grid(row=2, column=1, sticky="w", padx=(0, 18), pady=5)
        self.list_btn = ttk.Button(
            conn, text="Girişi Test Et / Bağlantıları Listele", command=self.on_list
        )
        self.list_btn.grid(row=2, column=2, columnspan=2, sticky="w", pady=5)

        # Zamanlama
        timing = ttk.LabelFrame(main, text=" Zamanlama ", padding=(12, 8))
        timing.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        group = ttk.Frame(timing)
        group.pack(side="left", padx=(0, 26))
        ttk.Label(group, text="Her").pack(side="left")
        self.interval_var = tk.StringVar(value="2")
        ttk.Spinbox(
            group, from_=1, to=1440, textvariable=self.interval_var, width=5, justify="center"
        ).pack(side="left", padx=4)
        ttk.Label(group, text="dakikada bir").pack(side="left")

        group = ttk.Frame(timing)
        group.pack(side="left", padx=(0, 26))
        ttk.Label(group, text="Kesme beklemesi:").pack(side="left")
        self.wait_var = tk.StringVar(value="6")
        ttk.Spinbox(
            group, from_=0, to=120, textvariable=self.wait_var, width=5, justify="center"
        ).pack(side="left", padx=4)
        ttk.Label(group, text="sn").pack(side="left")

        group = ttk.Frame(timing)
        group.pack(side="left")
        ttk.Label(group, text="Bağlanma zaman aşımı:").pack(side="left")
        self.timeout_var = tk.StringVar(value="75")
        ttk.Spinbox(
            group, from_=15, to=600, textvariable=self.timeout_var, width=5, justify="center"
        ).pack(side="left", padx=4)
        ttk.Label(group, text="sn").pack(side="left")

        # Düğmeler
        actions = ttk.Frame(main)
        actions.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.start_btn = ttk.Button(actions, text="Başlat", command=self.on_start)
        self.start_btn.pack(side="left", padx=(0, 6))
        self.stop_btn = ttk.Button(actions, text="Durdur", command=self.on_stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 6))
        self.once_btn = ttk.Button(
            actions, text="IP'yi Şimdi Değiştir", command=self.on_once
        )
        self.once_btn.pack(side="left", padx=(0, 6))
        self.save_btn = ttk.Button(actions, text="Ayarları Kaydet", command=self.on_save)
        self.save_btn.pack(side="left")

        # Durum
        status_frame = ttk.LabelFrame(main, text=" Durum ", padding=(12, 8))
        status_frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        status_frame.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Hazır")
        self.status_label = ttk.Label(
            status_frame, textvariable=self.status_var, style="StatusOk.TLabel", anchor="w"
        )
        self.status_label.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.ip_var = tk.StringVar(value="Mevcut IP: —")
        ttk.Label(status_frame, textvariable=self.ip_var, style="Ip.TLabel").grid(
            row=1, column=0, sticky="w", pady=(5, 0)
        )
        self.countdown_var = tk.StringVar(value="Sonraki deneme: —")
        ttk.Label(status_frame, textvariable=self.countdown_var, style="Sub.TLabel").grid(
            row=1, column=1, sticky="e", pady=(5, 0)
        )

        # Günlük
        log_frame = ttk.LabelFrame(main, text=" Günlük ", padding=(8, 6))
        log_frame.grid(row=5, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = ScrolledText(
            log_frame,
            height=12,
            wrap="word",
            font=("Consolas", 9),
            state="disabled",
            borderwidth=1,
            relief="solid",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_configure("info", foreground="#1f2937")
        self.log_text.tag_configure("dim", foreground="#6b7280")
        self.log_text.tag_configure("success", foreground="#15803d")
        self.log_text.tag_configure("warn", foreground="#b45309")
        self.log_text.tag_configure("error", foreground="#b91c1c")

        log_buttons = ttk.Frame(log_frame)
        log_buttons.grid(row=1, column=0, sticky="e", pady=(6, 0))
        ttk.Button(
            log_buttons, text="Günlüğü Temizle", command=self.on_clear_log
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            log_buttons, text="Günlük Dosyasını Aç", command=self.on_open_log
        ).pack(side="left")

    def _load_settings_into_ui(self) -> None:
        self.host_var.set(self.settings.host)
        self.user_var.set(self.settings.username)
        self.target_var.set(self.settings.target)
        self.interval_var.set(str(max(1, self.settings.interval_sec // 60)))
        self.wait_var.set(str(self.settings.disconnect_wait))
        self.timeout_var.set(str(self.settings.connect_timeout))
        if self.settings.has_password():
            self._log("dim", "Kayıtlı şifre bulundu; şifre alanı boş bırakılabilir.")

    def _toggle_pass(self) -> None:
        self.pass_entry.configure(show="" if self.show_pass_var.get() else "•")

    # -- durum ve günlük ----------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)
        low = text.lower()
        if any(word in low for word in ("hata", "başarısız", "doğrulanamadı")):
            style = "StatusErr.TLabel"
        elif text.startswith("Durduruldu"):
            style = "StatusIdle.TLabel"
        elif any(word in low for word in ("tamamlandı", "hazır", "beklemede")):
            style = "StatusOk.TLabel"
        else:
            style = "StatusRun.TLabel"
        self.status_label.configure(style=style)

    def _log(self, level: str, message: str) -> None:
        if level not in ("info", "dim", "success", "warn", "error"):
            level = "info"
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", line + "\n", level)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except tk.TclError:
            pass
        append_file_log(f"{now_text()} [{level.upper()}] {message}")

    def _tk_exception(self, exc_type, value, tb) -> None:
        import traceback

        detail = "".join(traceback.format_exception(exc_type, value, tb))
        try:
            self._log("error", f"Arayüz hatası: {value}")
        except Exception:
            pass
        append_file_log(detail)

    def _update_buttons(self) -> None:
        idle = not self.running and not self.busy
        self.start_btn.configure(state="normal" if idle else "disabled")
        self.once_btn.configure(state="normal" if idle else "disabled")
        self.list_btn.configure(state="normal" if idle else "disabled")
        self.save_btn.configure(state="normal" if not self.busy else "disabled")
        self.stop_btn.configure(
            state="normal" if (self.running and not self.stopping) else "disabled"
        )


    # -- ayar okuma / kaydetme ---------------------------------------------

    def _read_settings_from_ui(self, require_password: bool) -> Settings | None:
        host = normalize_host(self.host_var.get())
        if not host:
            messagebox.showwarning(
                "Eksik bilgi", "Modem adresi gerekli. Örnek: 192.168.1.1",
                parent=self.root,
            )
            return None
        username = self.user_var.get().strip()
        if not username:
            messagebox.showwarning(
                "Eksik bilgi", "Modem yönetici kullanıcı adı gerekli.",
                parent=self.root,
            )
            return None
        target = self.target_var.get().strip()

        try:
            interval_min = int(self.interval_var.get().strip())
            wait_sec = int(self.wait_var.get().strip())
            timeout_sec = int(self.timeout_var.get().strip())
        except ValueError:
            messagebox.showwarning(
                "Geçersiz değer",
                "Zamanlama alanlarına tam sayı girin.",
                parent=self.root,
            )
            return None
        if interval_min < 1:
            messagebox.showwarning(
                "Geçersiz değer", "Aralık en az 1 dakika olmalı.", parent=self.root
            )
            return None

        settings = Settings(
            host=host,
            username=username,
            target=target,
            interval_sec=interval_min * 60,
            disconnect_wait=max(0, min(wait_sec, 300)),
            connect_timeout=max(15, min(timeout_sec, 600)),
            password_dpapi=self.settings.password_dpapi,
            password_plain=self.settings.password_plain,
        )
        typed_password = self.pass_var.get()
        if typed_password:
            settings.set_password(typed_password)

        if require_password and not settings.has_password():
            messagebox.showwarning(
                "Şifre gerekli",
                "Modem yönetici şifresini girin.",
                parent=self.root,
            )
            self.pass_entry.focus_set()
            return None
        return settings

    # -- düğme eylemleri ----------------------------------------------------

    def on_start(self) -> None:
        if self.running or self.busy:
            return
        settings = self._read_settings_from_ui(require_password=True)
        if settings is None:
            return
        try:
            save_settings(settings)
        except OSError as exc:
            messagebox.showerror(
                "Ayarlar kaydedilemedi",
                f"Ayar dosyası yazılamadı:\n{CONFIG_FILE}\n\n{exc}",
                parent=self.root,
            )
            return
        self.settings = settings
        self.stop_event = threading.Event()
        self.running = True
        self.stopping = False
        self.auth_failed = False
        self.next_run = None
        self._update_buttons()
        self._set_status("Başlatılıyor...")
        self._log(
            "info",
            f"Başlatıldı — her {settings.interval_sec // 60} dakikada bir "
            "IP değiştirilecek.",
        )
        self._log(
            "dim",
            f"Hedef: {settings.target or '(otomatik)'} • "
            f"kesme beklemesi: {settings.disconnect_wait} sn • "
            f"zaman aşımı: {settings.connect_timeout} sn",
        )
        self.worker = threading.Thread(
            target=self._loop,
            args=(settings, self.stop_event),
            daemon=True,
            name="wan-ip-loop",
        )
        self.worker.start()

    def on_stop(self) -> None:
        if not self.running:
            return
        self.stopping = True
        self.stop_event.set()
        self._set_status("Durduruluyor...")
        self._log("info", "Durdurma isteği alındı; mevcut işlem bitince duracak.")
        self._update_buttons()

    def on_once(self) -> None:
        if self.running or self.busy:
            return
        settings = self._read_settings_from_ui(require_password=True)
        if settings is None:
            return
        try:
            save_settings(settings)
        except OSError as exc:
            messagebox.showerror(
                "Ayarlar kaydedilemedi",
                f"Ayar dosyası yazılamadı:\n{CONFIG_FILE}\n\n{exc}",
                parent=self.root,
            )
            return
        self.settings = settings
        self.busy = True
        self.auth_failed = False
        self._update_buttons()
        self._set_status("IP değiştiriliyor...")
        self._log("info", "Tek seferlik IP değiştirme başlatıldı.")
        threading.Thread(
            target=self._once_worker,
            args=(settings,),
            daemon=True,
            name="wan-ip-once",
        ).start()

    def on_list(self) -> None:
        if self.running or self.busy:
            return
        settings = self._read_settings_from_ui(require_password=True)
        if settings is None:
            return
        self.settings = settings
        self.busy = True
        self.auth_failed = False
        self._update_buttons()
        self._set_status("Bağlantılar okunuyor...")
        self._log("info", "Modeme giriş yapılıyor ve WAN bağlantıları listeleniyor...")
        threading.Thread(
            target=self._list_worker,
            args=(settings,),
            daemon=True,
            name="wan-ip-list",
        ).start()

    def on_save(self) -> None:
        settings = self._read_settings_from_ui(require_password=False)
        if settings is None:
            return
        try:
            save_settings(settings)
        except OSError as exc:
            messagebox.showerror(
                "Ayarlar kaydedilemedi",
                f"Ayar dosyası yazılamadı:\n{CONFIG_FILE}\n\n{exc}",
                parent=self.root,
            )
            return
        self.settings = settings
        self._log("success", "Ayarlar kaydedildi.")

    def on_clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def on_open_log(self) -> None:
        if not LOG_FILE.exists():
            messagebox.showinfo(
                "Günlük dosyası",
                "Henüz günlük dosyası oluşmadı.",
                parent=self.root,
            )
            return
        try:
            os.startfile(str(LOG_FILE))
        except OSError as exc:
            messagebox.showerror(
                "Dosya açılamadı", f"{LOG_FILE}\n\n{exc}", parent=self.root
            )

    # -- arka plan işleri ---------------------------------------------------

    def _loop(self, settings: Settings, stop: threading.Event) -> None:
        post = self.queue.put
        first = True
        while not stop.is_set():
            if not first:
                next_run = time.time() + settings.interval_sec
                post(("next_run", next_run))
                if stop.wait(settings.interval_sec):
                    break
            first = False
            post(("next_run", None))
            post(("status", "IP değiştiriliyor..."))
            try:
                self._cycle(settings, stop, post)
                if not stop.is_set():
                    post(("status", "Beklemede"))
            except AuthError as exc:
                post(("log", "error", str(exc)))
                post(("auth_failed", str(exc)))
                break
            except RouterError as exc:
                post(("log", "error", f"Döngü hatası: {exc}"))
                post(("status", "Hata — sonraki deneme beklenecek"))
            except Exception as exc:  # beklenmeyen hata döngüyü durdurmasın
                post(("log", "error", f"Beklenmeyen hata: {exc!r}"))
                post(("status", "Hata — sonraki deneme beklenecek"))
        post(("next_run", None))
        post(("loop_end", None))

    def _cycle(self, settings: Settings, stop: threading.Event, post) -> None:
        client = RouterClient(
            settings.host, settings.username, settings.password(), timeout=12
        )
        try:
            post(("status", "Modeme giriş yapılıyor..."))
            client.login()
            post(("log", "dim", "Giriş başarılı."))
            if stop.is_set():
                return

            entries = client.list_wan()
            entry = choose_entry(entries, settings.target)
            if entry is None:
                names = ", ".join(e.get("name", "?") for e in entries) or "(kayıt yok)"
                raise RouterError(
                    f"'{settings.target}' adlı WAN bağlantısı bulunamadı. "
                    f"Mevcut kayıtlar: {names}. "
                    "'Girişi Test Et / Bağlantıları Listele' ile doğru adı seçin."
                )

            name = entry.get("name", "?")
            stack = entry["__stack"]
            state = entry.get("connectionStatus", "?")
            old_ip = clean_ip(entry.get("externalIPAddress"))
            post(
                (
                    "log",
                    "info",
                    f"Hedef: {name} • durum: {state} • "
                    f"IP: {old_ip or 'yok'} • stack: {stack}",
                )
            )
            if old_ip:
                post(("ip", old_ip))
            if stop.is_set():
                return

            if state == "Connected":
                post(("status", f"{name} kesiliyor..."))
                client.ppp_action("ACT_PPP_DISCONN", stack)
                post(("log", "info", "Bağlantı kesildi."))
                if stop.wait(max(0, settings.disconnect_wait)):
                    post(
                        (
                            "log",
                            "warn",
                            "Durdurma istendi; internetin kapalı kalmaması "
                            "için bağlantı yine de yeniden kurulacak.",
                        )
                    )
            else:
                post(
                    (
                        "log",
                        "warn",
                        f"Bağlantı zaten '{state}' durumunda; "
                        "kesme adımı atlandı.",
                    )
                )

            post(("status", f"{name} yeniden bağlanıyor..."))
            client.ppp_action("ACT_PPP_CONN", stack)
            post(
                (
                    "log",
                    "info",
                    "Bağlanma komutu gönderildi; yeni IP bekleniyor...",
                )
            )

            deadline = time.time() + max(15, settings.connect_timeout)
            new_ip = ""
            last_state = ""
            stopped_early = False
            while time.time() < deadline:
                if stop.wait(3):
                    stopped_early = True
                    break
                entries = client.list_wan()
                current = find_entry(entries, name, stack)
                if current is None:
                    continue
                current_state = current.get("connectionStatus", "")
                if current_state != last_state:
                    last_state = current_state
                    post(("log", "dim", f"Durum: {current_state or '?'}"))
                current_ip = clean_ip(current.get("externalIPAddress"))
                if current_state == "Connected" and current_ip:
                    new_ip = current_ip
                    break

            if stopped_early:
                post(
                    (
                        "log",
                        "warn",
                        "Durdurma istendi; bağlanma komutu gönderildi. "
                        "Bağlantı modem tarafından kurulacak.",
                    )
                )
                post(("status", "Durduruldu"))
                return

            if not new_ip:
                post(
                    (
                        "log",
                        "warn",
                        "Zaman aşımı: bağlantı kurulamadı veya IP alınamadı. "
                        "Modem arayüzünden DSL durumunu kontrol edin.",
                    )
                )
                post(("status", "Bağlantı doğrulanamadı"))
                return

            post(("ip", new_ip))
            post(("status", "Tamamlandı"))
            if old_ip and new_ip == old_ip:
                post(
                    (
                        "log",
                        "warn",
                        f"Yeni IP: {new_ip} — IP değişmedi. ISS aynı adresi "
                        "yeniden atamış olabilir; kesme beklemesini artırmayı "
                        "deneyin.",
                    )
                )
            elif old_ip:
                post(("log", "success", f"IP değişti: {old_ip} → {new_ip}"))
            else:
                post(("log", "success", f"Bağlantı kuruldu. Yeni IP: {new_ip}"))
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _once_worker(self, settings: Settings) -> None:
        stop = threading.Event()
        post = self.queue.put
        try:
            self._cycle(settings, stop, post)
        except AuthError as exc:
            post(("log", "error", str(exc)))
            post(("auth_failed", str(exc)))
        except RouterError as exc:
            post(("log", "error", str(exc)))
            post(("status", "Hata"))
        except Exception as exc:
            post(("log", "error", f"Beklenmeyen hata: {exc!r}"))
            post(("status", "Hata"))
        finally:
            post(("busy_end", None))

    def _list_worker(self, settings: Settings) -> None:
        client = RouterClient(
            settings.host, settings.username, settings.password(), timeout=12
        )
        post = self.queue.put
        try:
            post(("log", "dim", "Giriş yapılıyor..."))
            client.login()
            entries = client.list_wan()
            rows = [
                {
                    "name": entry.get("name", "?"),
                    "status": entry.get("connectionStatus", "?"),
                    "ip": clean_ip(entry.get("externalIPAddress")),
                    "stack": entry.get("__stack", "?"),
                }
                for entry in entries
            ]
            post(("entries", rows))
            post(("log", "success", f"{len(rows)} PPPoE bağlantısı bulundu."))
            post(("status", "Liste hazır"))
        except AuthError as exc:
            post(("log", "error", str(exc)))
            post(("auth_failed", str(exc)))
        except RouterError as exc:
            post(("log", "error", str(exc)))
            post(("status", "Hata"))
        except Exception as exc:
            post(("log", "error", f"Beklenmeyen hata: {exc!r}"))
            post(("status", "Hata"))
        finally:
            try:
                client.logout()
            except Exception:
                pass
            post(("busy_end", None))

    # -- kuyruk / zamanlayıcı ----------------------------------------------

    def _handle_entries(self, rows: list[dict]) -> None:
        names = [row["name"] for row in rows if row.get("name")]
        self.target_combo.configure(values=names)
        current = self.target_var.get().strip()
        connected = [
            row for row in rows
            if row.get("status") == "Connected" and row.get("name")
        ]
        if current not in names:
            if len(connected) == 1:
                self.target_var.set(connected[0]["name"])
                self._log(
                    "info",
                    f"Hedef otomatik seçildi: {connected[0]['name']}",
                )
            elif not current and names:
                self.target_var.set(names[0])
        for row in rows:
            self._log(
                "info",
                f"  • {row['name']} — {row['status']} — "
                f"{row['ip'] or 'IP yok'} — stack {row['stack']}",
            )
        if connected and connected[0].get("ip"):
            self.ip_var.set(f"Mevcut IP: {connected[0]['ip']}")

    def _drain_queue(self) -> None:
        try:
            while True:
                message = self.queue.get_nowait()
                kind = message[0]
                if kind == "log":
                    self._log(message[1], message[2])
                elif kind == "status":
                    self._set_status(message[1])
                elif kind == "ip":
                    self.ip_var.set(f"Mevcut IP: {message[1]}")
                elif kind == "next_run":
                    self.next_run = message[1]
                elif kind == "entries":
                    self._handle_entries(message[1])
                elif kind == "auth_failed":
                    self.auth_failed = True
                    self._set_status("Durduruldu — giriş başarısız")
                    messagebox.showerror(
                        "Giriş başarısız", message[1], parent=self.root
                    )
                elif kind == "loop_end":
                    self.running = False
                    self.stopping = False
                    self.next_run = None
                    if not self.auth_failed:
                        self._set_status("Durduruldu")
                    self.auth_failed = False
                    self._update_buttons()
                elif kind == "busy_end":
                    self.busy = False
                    self.auth_failed = False
                    self._update_buttons()
        except queue.Empty:
            pass
        self.root.after(150, self._drain_queue)

    def _tick(self) -> None:
        if self.running and self.next_run is not None:
            remaining = max(0, int(self.next_run - time.time()))
            self.countdown_var.set(
                f"Sonraki deneme: {remaining // 60:02d}:{remaining % 60:02d}"
            )
        elif self.running:
            self.countdown_var.set("Sonraki deneme: işlem sürüyor...")
        else:
            self.countdown_var.set("Sonraki deneme: —")
        self.root.after(250, self._tick)

    def _on_close(self) -> None:
        if self.running or self.busy:
            if not messagebox.askyesno(
                "Çıkış",
                "Bir işlem sürüyor. Şimdi çıkarsanız WAN bağlantısı "
                "kapalı kalabilir.\n\nYine de çıkılsın mı?",
                parent=self.root,
            ):
                return
        self.stop_event.set()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Kendi kendini test (python wan_ip_degistirici.pyw --selftest)
# ---------------------------------------------------------------------------

def _is_probable_prime(number: int, rounds: int = 24) -> bool:
    if number < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for prime in small_primes:
        if number % prime == 0:
            return number == prime
    d = number - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        base = secrets.randbelow(number - 3) + 2
        value = pow(base, d, number)
        if value in (1, number - 1):
            continue
        for _ in range(s - 1):
            value = pow(value, 2, number)
            if value == number - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def run_selftest() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"[OK]   {name}")
        else:
            print(f"[FAIL] {name}" + (f" — {detail}" if detail else ""))
            failures.append(name)

    # 1) CGI yanıt ayrıştırma
    sample = (
        "[1,1,1,0,0,0]0\r\n"
        "name=dsl_internet\r\n"
        "connectionStatus=Connected\r\n"
        "externalIPAddress=88.241.10.20\r\n"
        "connectionType=IP_Routed\r\n"
        "addressingType=DHCP\r\n"
        "[2,1,1,0,0,0]0\r\n"
        "name=dsl_iptv\r\n"
        "connectionStatus=Disconnected\r\n"
        "externalIPAddress=0.0.0.0\r\n"
        "[error]0\r\n"
    )
    entries = parse_cgi_entries(sample)
    check("CGI: iki kayıt ayrıştırıldı", len(entries) == 2, f"len={len(entries)}")
    check(
        "CGI: stack doğru",
        entries and entries[0].get("__stack") == "1,1,1,0,0,0",
    )
    check(
        "CGI: ad ve durum doğru",
        entries and entries[0].get("name") == "dsl_internet"
        and entries[0].get("connectionStatus") == "Connected",
    )
    check(
        "CGI: IP doğru",
        entries and entries[0].get("externalIPAddress") == "88.241.10.20",
    )
    check(
        "CGI: [error] satırı kayıt sayılmadı",
        all("__stack" in entry for entry in entries),
    )
    check(
        "Seçim: tam ad eşleşmesi",
        choose_entry(entries, "dsl_internet") is entries[0],
    )
    check("Seçim: bilinmeyen ad None", choose_entry(entries, "yok") is None)
    check(
        "Seçim: boş hedefte bağlı olan",
        choose_entry(entries, "") is entries[0],
    )
    check(
        "Seçim: stack ile bulma",
        find_entry(entries, "dsl_internet", "1,1,1,0,0,0") is entries[0],
    )

    # 2) Adres yardımcıları
    check(
        "Adres: http:// ve / temizleniyor",
        normalize_host("http://192.168.1.1/") == "192.168.1.1",
    )
    check("Adres: boş girdi", normalize_host("   ") == "")
    check("IP: 0.0.0.0 boş sayılıyor", clean_ip("0.0.0.0") == "")
    check("IP: geçerli IP korunuyor", clean_ip(" 1.2.3.4 ") == "1.2.3.4")

    # 3) Giriş sayfası sezgisi
    check(
        "Giriş sayfası tanınıyor",
        looks_like_login_page('<html><input id="pc-login-password"></html>'),
    )
    check(
        "CGI yanıtı giriş sayfası sanılmıyor",
        not looks_like_login_page("[1,1,1,0,0,0]0\r\nname=x\r\n[error]0\r\n"),
    )

    # 4) RSA / PKCS#1 v1.5
    p = _gen_prime(64)
    q = _gen_prime(64)
    while q == p:
        q = _gen_prime(64)
    n = p * q
    e = 65537
    d = pow(e, -1, (p - 1) * (q - 1))
    message = b"admin"
    hex_value = rsa_encrypt(message, n, e)
    k = (n.bit_length() + 7) // 8
    check("RSA: hex uzunluğu modulusa eşit", len(hex_value) == k * 2)
    check("RSA: küçük harf hex", hex_value == hex_value.lower())
    decoded = pow(int(hex_value, 16), d, n).to_bytes(k, "big")
    check(
        "RSA: PKCS#1 tip 2 yapısı",
        decoded[:2] == b"\x00\x02" and decoded.endswith(b"\x00" + message),
    )
    separator = decoded.rfind(b"\x00")
    check("RSA: en az 8 bayt dolgu", separator >= 10, f"separator={separator}")
    check(
        "RSA: dolgu baytları sıfır değil",
        b"\x00" not in decoded[2:separator],
    )
    fake_n = (1 << 1023) | 1
    fake_hex = rsa_encrypt(b"x", fake_n, 65537)
    check("RSA: 1024-bit çıktı 256 hex", len(fake_hex) == 256, f"len={len(fake_hex)}")

    # 5) Şifre saklama (Windows'ta DPAPI, değilse düz metin yedeği)
    settings = Settings()
    settings.set_password("gizli-şifre-123")
    check("Şifre: yazıldı", settings.has_password())
    check("Şifre: geri okundu", settings.password() == "gizli-şifre-123")
    if os.name == "nt":
        encoded = dpapi_protect("deneme")
        check("DPAPI: şifreleme", encoded is not None)
        if encoded:
            check("DPAPI: çözme", dpapi_unprotect(encoded) == "deneme")

    print()
    if failures:
        print(f"{len(failures)} test başarısız: {', '.join(failures)}")
        return 1
    print("TÜM TESTLER GEÇTİ")
    return 0


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------

def main() -> int:
    if "--selftest" in sys.argv:
        return run_selftest()

    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    smoke = "--smoke" in sys.argv
    if smoke:
        root.after(1000, root.destroy)
    root.mainloop()
    if smoke:
        print("GUI smoke test OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
