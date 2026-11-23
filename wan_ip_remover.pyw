# -*- coding: utf-8 -*-
"""
WAN IP Remover — TP-Link TD-W9970
================================

Signs in to the router's web UI, drops the selected PPPoE WAN connection and
brings it back up, so the ISP hands out a new public IP. The cycle repeats on
the chosen interval (two minutes by default).

Standard library only (tkinter included) — no external packages.

Run:
    pythonw wan_ip_remover.pyw

Test:
    python wan_ip_remover.pyw --selftest
"""

from __future__ import annotations

import base64
import ctypes
import http.cookiejar
import json
import math
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

APP_NAME = "WAN IP Remover"
APP_VERSION = "3.1.0"
TIMING_PRESETS = ("0.1", "0.32", "1", "2", "5")
APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "config.json"
LOG_FILE = APP_DIR / "wan_ip_remover.log"
MAX_LOG_BYTES = 1_000_000

LANG = "en"
FORCED_LANG: str | None = None

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "brand.suffix": "REMOVER",
        "app.tagline": "TP-Link TD-W9970 · PPPoE session renewer",
        "state.ready": "READY",
        "state.running": "RUNNING",
        "state.stopped": "STOPPED",
        "state.error": "ERROR",
        "state.warn": "CHECK",
        "core.ip_label": "PUBLIC IP ADDRESS",
        "core.hint_empty": "Not read yet · click the IP to copy",
        "core.hint_known": "Last change {time} · click to copy",
        "core.hint_read": "Read from router · click to copy",
        "meta.line": "Target {target}   ·   interval {minutes} min   ·   gap {wait} s",
        "btn.start": "Start",
        "btn.stop": "Stop",
        "btn.once": "Run once",
        "btn.save": "Save",
        "btn.list": "List",
        "btn.show": "Show",
        "btn.hide": "Hide",
        "btn.check": "Check",
        "btn.install": "Install",
        "btn.clear": "Clear",
        "btn.file": "Log file",
        "stats.cycles": "CYCLES",
        "stats.last_change": "LAST CHANGE",
        "stats.uptime": "UPTIME",
        "stats.recent": "RECENT CYCLES",
        "stats.waiting": "waiting for a cycle",
        "conn.title": "Connection",
        "conn.hint": "router access",
        "conn.host": "ROUTER ADDRESS",
        "conn.user": "USERNAME",
        "conn.pass": "ROUTER PASSWORD",
        "conn.target": "TARGET WAN CONNECTION",
        "conn.dpapi": "Encrypted with DPAPI",
        "timing.title": "Timing",
        "timing.hint": "cycle interval",
        "timing.interval": "Interval",
        "timing.gap": "Disconnect gap",
        "timing.timeout": "Connect timeout",
        "unit.min": "min",
        "unit.sec": "s",
        "log.title": "Console",
        "log.hint": "live stream",
        "update.title": "Updates",
        "update.checking": "Checking GitHub releases…",
        "update.current": "Up to date — v{version}",
        "update.available": "New version ready: v{version}",
        "update.downloading": "Downloading… {percent}%",
        "update.downloading_kb": "Downloading… {percent}% ({kb} KB)",
        "update.failed_check": "Check failed: {error}",
        "update.failed_download": "Update could not be downloaded.",
        "update.cancelled": "Install cancelled.",
        "update.failed_install": "Update could not be applied.",
        "update.err_http": "GitHub replied with HTTP {status}.",
        "update.err_json": "The GitHub reply could not be read.",
        "update.err_temp": "The temporary folder could not be created: {error}",
        "update.err_download": "Download failed: {error}",
        "update.err_small": "The downloaded file is smaller than expected.",
        "update.err_read": "The file could not be read: {error}",
        "update.err_version": "The downloaded file's version could not be verified.",
        "update.err_identity": "The downloaded file does not look like this app.",
        "update.err_syntax": "The downloaded file has a syntax error: {error}",
        "update.err_copy": "The new version could not be copied: {error}",
        "update.err_launch": "The updater could not be started: {error}",
        "update.button": "Install v{version}",
        "update.install_prompt": (
            "Install v{version}?\n\nThe app will close, the file will be replaced "
            "and restarted. The old version is kept as .bak."
        ),
        "update.installing_log": "v{version} will be installed; restarting…",
        "update.downloaded_log": "v{version} downloaded and verified.",
        "update.found_log": "New version found: v{version} ({tag})",
        "update.none_log": "No update; you are on the latest version.",
        "footer.left": "Passwords are encrypted with Windows DPAPI · updates via GitHub Releases",
        "status.starting": "Starting…",
        "status.stopping": "Stopping…",
        "status.changing_ip": "Changing IP…",
        "status.logging_in": "Signing in to the router…",
        "status.reading_links": "Reading connections…",
        "status.idle": "Idle",
        "status.done": "Done",
        "status.retry": "Error — retrying next cycle",
        "status.unverified": "Connection not verified",
        "status.list_ready": "List ready",
        "status.stopped": "Stopped",
        "status.stopped_auth": "Stopped — sign-in failed",
        "status.error": "Error",
        "status.disconnecting": "{name} disconnecting…",
        "status.reconnecting": "{name} reconnecting…",
        "tick.next": "next cycle",
        "log.signing_in": "Signing in…",
        "log.ui_error": "UI error: {error}",
        "meta.auto": "auto",
        "err.ip_none": "none",
        "msg.update_error_title": "Update error",
        "log.ready": "{app} v{version} ready.",
        "log.tip": (
            "Tip: don't keep the router's web UI open in another browser; "
            "the TD-W9970 allows a single admin session."
        ),
        "log.saved_password": "Saved password found; you can leave the password field empty.",
        "log.started": "Started — the IP will change every {span}.",
        "log.target_line": "Target: {target} • disconnect gap: {wait} s • timeout: {timeout} s",
        "log.once_started": "One-off IP change started.",
        "log.list_started": "Signing in and listing WAN connections…",
        "log.settings_saved": "Settings saved.",
        "log.stop_requested": "Stop requested; it will stop after the current cycle.",
        "log.login_ok": "Signed in.",
        "log.target_state": "Target: {name} • state: {state} • IP: {ip} • stack: {stack}",
        "log.disconnected": "Connection closed.",
        "log.stop_during_gap": "Stop requested; the connection will still be brought back up.",
        "log.already_state": "Connection is already '{state}'; disconnect step skipped.",
        "log.reconnect_cmd": "Reconnect command sent; waiting for the new IP…",
        "log.state_change": "State: {state}",
        "log.stop_early": "Stop requested; the reconnect command was sent. The router will finish it.",
        "log.timeout": (
            "Timeout: the connection was not established or no IP was assigned. "
            "Check DSL status in the router."
        ),
        "log.same_ip": (
            "New IP: {ip} — the IP did not change. Your ISP may have reassigned "
            "the same address; try a longer disconnect gap."
        ),
        "log.ip_changed": "IP changed: {old} → {new}",
        "log.connected_ip": "Connected. New IP: {ip}",
        "log.cycle_error": "Cycle error: {error}",
        "log.unexpected": "Unexpected error: {error}",
        "log.entries": "{count} PPPoE connections found.",
        "log.entry_line": "  • {name} — {status} — {ip} — stack {stack}",
        "log.auto_target": "Target auto-selected: {name}",
        "log.update_check_failed": "Update check failed: {error}",
        "log.update_download_failed": "Update download failed: {error}",
        "log.install_error": "Update error: {error}",
        "msg.missing_info": "Missing information",
        "msg.host_required": "Router address is required. Example: 192.168.1.1",
        "msg.user_required": "Router admin username is required.",
        "msg.pass_title": "Password required",
        "msg.pass_required": "Enter the router admin password.",
        "msg.settings_title": "Settings could not be saved",
        "msg.settings_body": "Settings file could not be written:\n{path}\n\n{error}",
        "msg.auth_title": "Sign-in failed",
        "msg.exit_title": "Exit",
        "msg.exit_running": (
            "An operation is running. If you quit now the WAN connection may stay down.\n\n"
            "Quit anyway?"
        ),
        "msg.update_title": "Update",
        "msg.update_stop_first": "Stop the running operation before installing.",
        "msg.log_title": "Log file",
        "msg.log_missing": "No log file has been created yet.",
        "msg.open_error": "File could not be opened",
        "msg.copied": "{ip} copied",
        "select.connection": "Select a connection",
        "net.refused": "connection refused",
        "net.timeout": "timeout",
        "net.unknown": "unknown network error",
        "err.host_empty": "Router address cannot be empty.",
        "err.connect": "Could not reach the router ({base}): {reason}. Is the router on and is this PC on the same network?",
        "err.connect_short": "Could not reach the router ({base}): {reason}",
        "err.no_rsa": "The router did not provide its RSA key (/cgi/getParm). Is the address correct? {error}",
        "err.login_status": "The sign-in request returned an unexpected response (HTTP {status}).",
        "err.bad_credentials": "Wrong username or password.",
        "err.bad_request": "The router rejected the sign-in request.",
        "err.login_rejected": "The router rejected the sign-in (error code {code}).",
        "err.login_failed": "Sign-in failed: {reason}{details}\n\nThe router's web UI may be open in another browser; close it and try again.\nWARNING: after 5 failed attempts the router locks for 10 minutes. The program stopped for safety.",
        "err.attempts": "\nRouter failed-attempt counter: {count}",
        "err.lock": "\nRouter lock time: {seconds} s",
        "err.no_session": "Sign-in failed: no session cookie was created. The username/password may be wrong, or the router's web UI is open in another browser.\n\nWARNING: after 5 failed attempts the router locks for 10 minutes. The program stopped for safety.",
        "err.login_page": "Sign-in failed. The username/password may be wrong, or the router's web UI is open in another session.\n\nWARNING: after 5 failed attempts the router locks for 10 minutes. The program stopped for safety.",
        "err.session_http": "Session could not be opened (HTTP {status}). The router's web UI may be open in another browser; close it and try again.",
        "err.router_rejected": "The router rejected the request (HTTP {status}).",
        "err.session_lost": "The session seems to have dropped. The router's web UI may be open in another browser; close it and try again.",
        "err.no_wan": "Could not read the WAN list (router error code {code}).",
        "err.empty_wan": "The router returned an empty WAN list. This firmware may not support the command.",
        "err.action_response": "The router returned an unexpected response to '{action}': {text}",
        "err.action_rejected": "The router rejected '{action}' (error code {code}).",
        "err.target_missing": "No WAN connection named '{target}'. Available: {names}. Use 'List' to pick the right name.",
        "err.empty": "(empty)",
        "err.none": "(no entries)",
    },
    "tr": {
        "brand.suffix": "DEĞİŞTİRİCİ",
        "app.tagline": "TP-Link TD-W9970 · PPPoE oturum yenileyici",
        "state.ready": "HAZIR",
        "state.running": "ÇALIŞIYOR",
        "state.stopped": "DURDU",
        "state.error": "HATA",
        "state.warn": "KONTROL",
        "core.ip_label": "GENEL IP ADRESİ",
        "core.hint_empty": "Henüz okunmadı · IP'ye tıklayınca kopyalanır",
        "core.hint_known": "Son değişim {time} · kopyalamak için tıklayın",
        "core.hint_read": "Modemden okundu · kopyalamak için tıklayın",
        "meta.line": "Hedef {target}   ·   aralık {minutes} dk   ·   kesme {wait} sn",
        "btn.start": "Başlat",
        "btn.stop": "Durdur",
        "btn.once": "Tek tur",
        "btn.save": "Kaydet",
        "btn.list": "Listele",
        "btn.show": "Göster",
        "btn.hide": "Gizle",
        "btn.check": "Denetle",
        "btn.install": "Yükle",
        "btn.clear": "Temizle",
        "btn.file": "Dosya",
        "stats.cycles": "TUR",
        "stats.last_change": "SON DEĞİŞİM",
        "stats.uptime": "ÇALIŞMA",
        "stats.recent": "SON TURLAR",
        "stats.waiting": "tur bekleniyor",
        "conn.title": "Bağlantı",
        "conn.hint": "modem erişimi",
        "conn.host": "MODEM ADRESİ",
        "conn.user": "KULLANICI ADI",
        "conn.pass": "MODEM ŞİFRESİ",
        "conn.target": "HEDEF WAN BAĞLANTISI",
        "conn.dpapi": "DPAPI ile şifreli",
        "timing.title": "Zamanlama",
        "timing.hint": "tur aralığı",
        "timing.interval": "Aralık",
        "timing.gap": "Kesme beklemesi",
        "timing.timeout": "Bağlanma süresi",
        "unit.min": "dk",
        "unit.sec": "sn",
        "log.title": "Konsol",
        "log.hint": "canlı akış",
        "update.title": "Güncelleme",
        "update.checking": "GitHub sürümleri denetleniyor…",
        "update.current": "Güncel — v{version}",
        "update.available": "Yeni sürüm hazır: v{version}",
        "update.downloading": "İndiriliyor… %{percent}",
        "update.downloading_kb": "İndiriliyor… %{percent} ({kb} KB)",
        "update.failed_check": "Denetlenemedi: {error}",
        "update.failed_download": "Güncelleme indirilemedi.",
        "update.cancelled": "Yükleme iptal edildi.",
        "update.failed_install": "Güncelleme uygulanamadı.",
        "update.err_http": "GitHub yanıtı: HTTP {status}.",
        "update.err_json": "GitHub yanıtı okunamadı.",
        "update.err_temp": "Geçici klasör oluşturulamadı: {error}",
        "update.err_download": "İndirme başarısız: {error}",
        "update.err_small": "İndirilen dosya beklenenden küçük.",
        "update.err_read": "Dosya okunamadı: {error}",
        "update.err_version": "İndirilen dosyanın sürümü doğrulanamadı.",
        "update.err_identity": "İndirilen dosya bu uygulamaya ait görünmüyor.",
        "update.err_syntax": "İndirilen dosyada sözdizimi hatası: {error}",
        "update.err_copy": "Yeni sürüm kopyalanamadı: {error}",
        "update.err_launch": "Güncelleyici başlatılamadı: {error}",
        "update.button": "v{version} yükle",
        "update.install_prompt": (
            "v{version} yüklensin mi?\n\nUygulama kapanacak, dosya yenisiyle "
            "değiştirilecek ve yeniden başlatılacak. Eski sürüm .bak olarak saklanır."
        ),
        "update.installing_log": "v{version} yüklenecek; uygulama yeniden başlatılıyor…",
        "update.downloaded_log": "v{version} indirildi ve doğrulandı.",
        "update.found_log": "Yeni sürüm bulundu: v{version} ({tag})",
        "update.none_log": "Güncelleme yok; en son sürüm kullanılıyor.",
        "footer.left": "Şifreler Windows DPAPI ile şifrelenir · güncellemeler GitHub Releases üzerinden",
        "status.starting": "Başlatılıyor…",
        "status.stopping": "Durduruluyor…",
        "status.changing_ip": "IP değiştiriliyor…",
        "status.logging_in": "Modeme giriş yapılıyor…",
        "status.reading_links": "Bağlantılar okunuyor…",
        "status.idle": "Beklemede",
        "status.done": "Tamamlandı",
        "status.retry": "Hata — sonraki deneme beklenecek",
        "status.unverified": "Bağlantı doğrulanamadı",
        "status.list_ready": "Liste hazır",
        "status.stopped": "Durduruldu",
        "status.stopped_auth": "Durduruldu — giriş başarısız",
        "status.error": "Hata",
        "status.disconnecting": "{name} kesiliyor…",
        "status.reconnecting": "{name} yeniden bağlanıyor…",
        "tick.next": "sonraki tur",
        "log.signing_in": "Giriş yapılıyor…",
        "log.ui_error": "Arayüz hatası: {error}",
        "meta.auto": "otomatik",
        "err.ip_none": "yok",
        "msg.update_error_title": "Güncelleme hatası",
        "log.ready": "{app} v{version} hazır.",
        "log.tip": (
            "İpucu: modem arayüzünü başka bir tarayıcıda açık bırakmayın; "
            "TD-W9970 tek yönetici oturumu kabul eder."
        ),
        "log.saved_password": "Kayıtlı şifre bulundu; şifre alanı boş bırakılabilir.",
        "log.started": "Başlatıldı — IP {span} aralıkla değiştirilecek.",
        "log.target_line": "Hedef: {target} • kesme beklemesi: {wait} sn • zaman aşımı: {timeout} sn",
        "log.once_started": "Tek seferlik IP değiştirme başlatıldı.",
        "log.list_started": "Modeme giriş yapılıyor ve WAN bağlantıları listeleniyor…",
        "log.settings_saved": "Ayarlar kaydedildi.",
        "log.stop_requested": "Durdurma isteği alındı; mevcut işlem bitince duracak.",
        "log.login_ok": "Giriş başarılı.",
        "log.target_state": "Hedef: {name} • durum: {state} • IP: {ip} • stack: {stack}",
        "log.disconnected": "Bağlantı kesildi.",
        "log.stop_during_gap": "Durdurma istendi; internetin kapalı kalmaması için bağlantı yine de yeniden kurulacak.",
        "log.already_state": "Bağlantı zaten '{state}' durumunda; kesme adımı atlandı.",
        "log.reconnect_cmd": "Bağlanma komutu gönderildi; yeni IP bekleniyor…",
        "log.state_change": "Durum: {state}",
        "log.stop_early": "Durdurma istendi; bağlanma komutu gönderildi. Bağlantı modem tarafından kurulacak.",
        "log.timeout": "Zaman aşımı: bağlantı kurulamadı veya IP alınamadı. Modem arayüzünden DSL durumunu kontrol edin.",
        "log.same_ip": "Yeni IP: {ip} — IP değişmedi. ISS aynı adresi yeniden atamış olabilir; kesme beklemesini artırmayı deneyin.",
        "log.ip_changed": "IP değişti: {old} → {new}",
        "log.connected_ip": "Bağlantı kuruldu. Yeni IP: {ip}",
        "log.cycle_error": "Döngü hatası: {error}",
        "log.unexpected": "Beklenmeyen hata: {error}",
        "log.entries": "{count} PPPoE bağlantısı bulundu.",
        "log.entry_line": "  • {name} — {status} — {ip} — stack {stack}",
        "log.auto_target": "Hedef otomatik seçildi: {name}",
        "log.update_check_failed": "Güncelleme denetlenemedi: {error}",
        "log.update_download_failed": "Güncelleme indirilemedi: {error}",
        "log.install_error": "Güncelleme hatası: {error}",
        "msg.missing_info": "Eksik bilgi",
        "msg.host_required": "Modem adresi gerekli. Örnek: 192.168.1.1",
        "msg.user_required": "Modem yönetici kullanıcı adı gerekli.",
        "msg.pass_title": "Şifre gerekli",
        "msg.pass_required": "Modem yönetici şifresini girin.",
        "msg.settings_title": "Ayarlar kaydedilemedi",
        "msg.settings_body": "Ayar dosyası yazılamadı:\n{path}\n\n{error}",
        "msg.auth_title": "Giriş başarısız",
        "msg.exit_title": "Çıkış",
        "msg.exit_running": "Bir işlem sürüyor. Şimdi çıkarsanız WAN bağlantısı kapalı kalabilir.\n\nYine de çıkılsın mı?",
        "msg.update_title": "Güncelleme",
        "msg.update_stop_first": "Yükleme öncesi çalışan işlemi durdurun.",
        "msg.log_title": "Günlük dosyası",
        "msg.log_missing": "Henüz günlük dosyası oluşmadı.",
        "msg.open_error": "Dosya açılamadı",
        "msg.copied": "{ip} kopyalandı",
        "select.connection": "Bağlantı seçin",
        "net.refused": "bağlantı reddedildi",
        "net.timeout": "zaman aşımı",
        "net.unknown": "bilinmeyen ağ hatası",
        "err.host_empty": "Modem adresi boş olamaz.",
        "err.connect": "Modeme bağlanılamadı ({base}): {reason}. Modem açık mı ve bu bilgisayar aynı ağda mı?",
        "err.connect_short": "Modeme bağlanılamadı ({base}): {reason}",
        "err.no_rsa": "Modem RSA anahtarını vermedi (/cgi/getParm). Adres doğru mu? {error}",
        "err.login_status": "Giriş isteği beklenmeyen yanıt verdi (HTTP {status}).",
        "err.bad_credentials": "Kullanıcı adı veya şifre hatalı.",
        "err.bad_request": "Modem giriş isteğini geçersiz buldu.",
        "err.login_rejected": "Modem girişi reddetti (hata kodu {code}).",
        "err.login_failed": "Giriş başarısız: {reason}{details}\n\nModemin web arayüzü başka bir tarayıcıda açık olabilir; kapatıp tekrar deneyin.\nDİKKAT: 5 hatalı denemeden sonra modem 10 dakika kilitlenir. Program güvenlik için durduruldu.",
        "err.attempts": "\nModem hatalı deneme sayacı: {count}",
        "err.lock": "\nModem kilit süresi: {seconds} sn",
        "err.no_session": "Giriş başarısız: oturum çerezi oluşmadı. Kullanıcı adı/şifre hatalı olabilir veya modemin web arayüzü başka bir tarayıcıda açık olabilir.\n\nDİKKAT: 5 hatalı denemeden sonra modem 10 dakika kilitlenir. Program güvenlik için durduruldu.",
        "err.login_page": "Giriş başarısız. Kullanıcı adı/şifre hatalı olabilir veya modemin web arayüzü başka bir oturumda açık.\n\nDİKKAT: 5 hatalı denemeden sonra modem 10 dakika kilitlenir. Program güvenlik için durduruldu.",
        "err.session_http": "Oturum açılamadı (HTTP {status}). Modemin web arayüzü başka bir tarayıcıda açık olabilir; kapatıp tekrar deneyin.",
        "err.router_rejected": "Modem isteği reddetti (HTTP {status}).",
        "err.session_lost": "Oturum düşmüş görünüyor. Modemin web arayüzü başka bir tarayıcıda açık olabilir; kapatıp tekrar deneyin.",
        "err.no_wan": "WAN listesi alınamadı (modem hata kodu {code}).",
        "err.empty_wan": "Modem WAN listesi için boş yanıt verdi. Yazılım sürümü bu komutu desteklemiyor olabilir.",
        "err.action_response": "Modem '{action}' komutuna beklenmeyen yanıt verdi: {text}",
        "err.action_rejected": "Modem '{action}' komutunu reddetti (hata kodu {code}).",
        "err.target_missing": "'{target}' adlı WAN bağlantısı bulunamadı. Mevcut kayıtlar: {names}. 'Listele' ile doğru adı seçin.",
        "err.empty": "(boş)",
        "err.none": "(kayıt yok)",
    },
}


def t(key: str, **kwargs) -> str:
    table = STRINGS.get(LANG) or STRINGS["en"]
    text = table.get(key) or STRINGS["en"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def format_span(seconds: float) -> str:
    """'19 s' / '2 min' — compact, localised duration."""
    seconds = float(seconds or 0)
    if seconds < 60:
        return f"{round(seconds, 1):g} {t('unit.sec')}"
    text = f"{seconds / 60:.2f}".rstrip("0").rstrip(".") or "0"
    return f"{text} {t('unit.min')}"


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
# Log helpers
# ---------------------------------------------------------------------------

def now_text() -> str:
    return time.strftime("%d.%m.%Y %H:%M:%S")


def append_file_log(line: str) -> None:
    """Append to the log file; rotate it once it passes 1 MB."""
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
        # A failed log write never stops the program.
        pass


# ---------------------------------------------------------------------------
# Password storage via Windows DPAPI
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
    """Encrypt text with Windows DPAPI; returns base64, or None when unsupported."""
    if os.name != "nt":
        return None
    try:
        blob_in, keepalive = _make_blob(text.encode("utf-8"))
        blob_out = _DataBlob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in),
            ctypes.c_wchar_p("WAN IP Remover"),
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
    """Decrypt DPAPI base64 text; returns None on failure."""
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
    interval_sec: float = 19.2
    disconnect_wait: float = 2
    connect_timeout: int = 75
    password_dpapi: str = ""
    password_plain: str = ""
    language: str = "en"

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
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            setattr(settings, name, value)
    language = data.get("language")
    if language in ("tr", "en"):
        settings.language = language
    settings.interval_sec = round(max(3.0, min(float(settings.interval_sec), 86_400.0)), 1)
    settings.disconnect_wait = round(max(0.0, min(float(settings.disconnect_wait), 300.0)), 1)
    settings.connect_timeout = max(5, min(int(settings.connect_timeout), 600))
    return settings


def save_settings(settings: Settings) -> None:
    CONFIG_FILE.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Small helpers
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
    Split a TP-Link CGI response into records.

    Example:
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
    Return the record whose name matches exactly. An empty target picks the
    connected one, else the first. A given target that is missing yields None.
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
# RSA (PKCS#1 v1.5) — TP-Link's client-side password encryption
# ---------------------------------------------------------------------------

def rsa_encrypt(message: bytes, n: int, e: int) -> str:
    """
    RSA encryption with PKCS#1 v1.5 (type 2) padding.
    TP-Link expects lowercase hex of exactly modulus length.
    """
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 11:
        raise ValueError("RSA message too long")
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
    """Generic router communication error."""


class AuthError(RouterError):
    """Sign-in failed (wrong password, locked session, ...)."""


class RouterClient:
    """Client for the TP-Link TD-W9970 classic web UI."""

    def __init__(self, host: str, username: str, password: str, timeout: int = 12):
        self.host = normalize_host(host)
        if not self.host:
            raise RouterError(t("err.host_empty"))
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
            return t("net.refused")
        if isinstance(reason, TimeoutError):
            return t("net.timeout")
        text = str(reason or "")
        if "timed out" in text.lower():
            return t("net.timeout")
        return text or t("net.unknown")

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
                t("err.connect", base=self.base, reason=self._net_reason(exc.reason))
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise RouterError(
                t("err.connect_short", base=self.base, reason=self._net_reason(exc))
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
            t("err.no_rsa", error=last_error)
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
                t("err.login_status", status=status)
            )

        # TD-W9970 login reply: "$.ret=0;" on success, "$.ret=71233;" on error
        ret_match = re.search(r"\$\.ret\s*=\s*(-?\d+)", text)
        if ret_match and ret_match.group(1) != "0":
            code = int(ret_match.group(1))
            details = ""
            times_match = re.search(r"currAuthTimes\s*=\s*(\d+)", text)
            forbid_match = re.search(r"currForbidTime\s*=\s*(\d+)", text)
            if times_match:
                details += t("err.attempts", count=times_match.group(1))
            if forbid_match and int(forbid_match.group(1)) > 0:
                details += t("err.lock", seconds=forbid_match.group(1))
            if code == 71233:
                reason = t("err.bad_credentials")
            elif code == 71234:
                reason = t("err.bad_request")
            else:
                reason = t("err.login_rejected", code=code)
            raise AuthError(t("err.login_failed", reason=reason, details=details))

        if not self._has_cookie("JSESSIONID"):
            raise AuthError(t("err.no_session"))

        token = self._extract_token(text)
        index_status, index_text, _ = self._request("GET", "/", use_token=False)
        if index_status == 200:
            token = token or self._extract_token(index_text)
            if not token and looks_like_login_page(index_text):
                raise AuthError(t("err.login_page"))
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

    # -- CGI actions --------------------------------------------------------

    def _cgi(self, act: int, body: str) -> str:
        status, text, _ = self._request("POST", f"/cgi?{act}", data=body)
        if status in (401, 403):
            raise AuthError(t("err.session_http", status=status))
        if status != 200:
            raise RouterError(t("err.router_rejected", status=status))
        if looks_like_login_page(text):
            raise AuthError(t("err.session_lost"))
        return text

    def list_wan(self) -> list[dict]:
        body = "[WAN_PPP_CONN#0,0,0,0,0,0#0,0,0,0,0,0]0,0\r\n"
        text = self._cgi(5, body)
        entries = parse_cgi_entries(text)
        if not entries:
            error_match = re.search(r"\[error\](\d+)", text)
            if error_match and error_match.group(1) != "0":
                raise RouterError(t("err.no_wan", code=error_match.group(1)))
            raise RouterError(t("err.empty_wan"))
        return entries

    def ppp_action(self, action: str, stack: str) -> None:
        body = f"[{action}#{stack}#0,0,0,0,0,0]0,0\r\n"
        text = self._cgi(7, body)
        error_match = re.search(r"\[error\](\d+)", text)
        if error_match is None:
            raise RouterError(
                t("err.action_response", action=action,
                  text=text.strip()[:120] or t("err.empty"))
            )
        if error_match.group(1) != "0":
            raise RouterError(
                t("err.action_rejected", action=action, code=error_match.group(1))
            )


# ---------------------------------------------------------------------------
# GitHub update plumbing
# ---------------------------------------------------------------------------

GITHUB_OWNER = "umitsTASCI"
GITHUB_REPO = "wan-ip-remover"
RELEASES_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
UPDATE_ASSET = "wan_ip_remover.pyw"
UPDATE_BAT = "guncelle.bat"


class UpdateError(Exception):
    pass


def version_tuple(text: str) -> tuple[int, ...]:
    """'v2.1.3' / '2.1' -> (2, 1, 3) / (2, 1). Empty tuple when not found."""
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", text or "")
    if not match:
        return ()
    return tuple(int(part) for part in match.groups() if part is not None)


def is_newer(candidate: str, current: str) -> bool:
    new = version_tuple(candidate)
    old = version_tuple(current)
    if not new or not old:
        return False
    length = max(len(new), len(old))
    new += (0,) * (length - len(new))
    old += (0,) * (length - len(old))
    return new > old


@dataclass
class UpdateInfo:
    version: str
    tag: str
    url: str
    notes: str = ""
    size: int = 0


def parse_release(data: dict) -> UpdateInfo | None:
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name") or "")
    version = ".".join(str(part) for part in version_tuple(tag))
    if not version:
        return None
    for asset in data.get("assets") or []:
        if not isinstance(asset, dict) or asset.get("name") != UPDATE_ASSET:
            continue
        url = asset.get("browser_download_url")
        if not url:
            continue
        return UpdateInfo(
            version=version,
            tag=tag,
            url=str(url),
            notes=str(data.get("body") or ""),
            size=int(asset.get("size") or 0),
        )
    return None


class Updater:
    @staticmethod
    def check(timeout: int = 10) -> UpdateInfo | None:
        request = urllib.request.Request(
            RELEASES_API,
            headers={
                "User-Agent": f"{APP_NAME}/{APP_VERSION}",
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise UpdateError(t("update.err_http", status=exc.code)) from exc
        except urllib.error.URLError as exc:
            raise UpdateError(RouterClient._net_reason(exc.reason)) from exc
        except OSError as exc:
            raise UpdateError(str(exc)) from exc
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise UpdateError(t("update.err_json")) from exc
        info = parse_release(payload)
        if info and is_newer(info.version, APP_VERSION):
            return info
        return None

    @staticmethod
    def download(info: UpdateInfo, progress=None, timeout: int = 45) -> Path:
        request = urllib.request.Request(
            info.url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
        )
        folder = Path(tempfile.gettempdir()) / "wan_ip_update"
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise UpdateError(t("update.err_temp", error=exc)) from exc
        target = folder / UPDATE_ASSET
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                total = int(response.headers.get("Content-Length") or info.size or 0)
                done = 0
                with target.open("wb") as handle:
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        handle.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
        except urllib.error.URLError as exc:
            raise UpdateError(RouterClient._net_reason(exc.reason)) from exc
        except OSError as exc:
            raise UpdateError(t("update.err_download", error=exc)) from exc
        if target.stat().st_size < 10_000:
            raise UpdateError(t("update.err_small"))
        return target

    @staticmethod
    def validate(path: Path, version: str) -> None:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UpdateError(t("update.err_read", error=exc)) from exc
        marker = f'APP_VERSION = "{version}"'
        if marker not in source:
            raise UpdateError(t("update.err_version"))
        if "class RouterClient" not in source or "class App" not in source:
            raise UpdateError(t("update.err_identity"))
        try:
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            raise UpdateError(t("update.err_syntax", error=exc)) from exc

    @staticmethod
    def install(new_file: Path) -> None:
        target = APP_DIR / UPDATE_ASSET
        staged = APP_DIR / (Path(UPDATE_ASSET).stem + ".new.pyw")
        try:
            shutil.copyfile(new_file, staged)
        except OSError as exc:
            raise UpdateError(t("update.err_copy", error=exc)) from exc
        script = "\r\n".join(
            [
                "@echo off",
                "cd /d \"%~dp0\"",
                "ping -n 3 127.0.0.1 >nul",
                f"copy /y \"{UPDATE_ASSET}\" \"{UPDATE_ASSET}.bak\" >nul 2>&1",
                "set n=0",
                ":retry",
                f"move /y \"{staged.name}\" \"{UPDATE_ASSET}\" >nul 2>&1",
                "if not errorlevel 1 goto done",
                "set /a n+=1",
                "if %n% geq 40 goto fail",
                "ping -n 2 127.0.0.1 >nul",
                "goto retry",
                ":done",
                "start \"\" \"Start.bat\"",
                "goto quit",
                ":fail",
                f"del /f /q \"{staged.name}\" >nul 2>&1",
                "start \"\" \"Start.bat\"",
                ":quit",
                "(goto) 2>nul & del \"%~f0\"",
                "",
            ]
        )
        bat = APP_DIR / UPDATE_BAT
        try:
            bat.write_text(script, encoding="ascii", newline="")
            creation_flags = 0x08000000 if os.name == "nt" else 0
            subprocess.Popen(
                ["cmd", "/c", str(bat)],
                cwd=str(APP_DIR),
                creationflags=creation_flags,
                close_fds=True,
            )
        except OSError as exc:
            raise UpdateError(t("update.err_launch", error=exc)) from exc


# ---------------------------------------------------------------------------
# UI — the "Orbit" design language
# ---------------------------------------------------------------------------
#
# Design notes
# ---------------
# * Unit: a 96 DPI design unit; px() scales it to the real DPI.
# * Type: Bahnschrift (display), Segoe UI Variable Text (body),
#   Cascadia Mono (numbers / IP / log). All ship with Windows.
# * Palette: one phosphor-lime accent; everything else is neutral carbon.
# * Focal element: the orbital gauge (ticked dial + progress arc + end dot).

SC = 1.0


def px(value: float) -> int:
    return int(round(value * SC))


def enable_dpi_awareness() -> None:
    """Must run before the Tk window exists; otherwise Windows scales the
    whole UI as a bitmap and every glyph turns blurry."""
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def init_scale(root: tk.Misc) -> None:
    global SC
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except Exception:
        dpi = 96.0
    if dpi < 72 or dpi > 480:
        dpi = 96.0
    SC = max(1.0, min(2.5, dpi / 96.0))
    try:
        root.tk.call("tk", "scaling", dpi / 72.0)
    except tk.TclError:
        pass


class C:
    bg = "#06070A"
    panel = "#0B0E12"
    panel2 = "#12161B"
    panel3 = "#181D24"
    input = "#080A0D"
    line = "#1B2026"
    line2 = "#2A313A"
    text = "#F3F5F8"
    muted = "#9AA4B2"
    dim = "#5F6875"
    lime = "#C9F75A"
    lime_hi = "#DCFF86"
    lime_lo = "#A8D43C"
    lime_deep = "#28330F"
    green = "#57E39B"
    cyan = "#5CD8FF"
    amber = "#FFC24B"
    red = "#FF6B6B"


FONT_UI = "Segoe UI"
FONT_DISPLAY = "Bahnschrift"
FONT_MONO = "Consolas"


def setup_fonts(root: tk.Misc) -> None:
    global FONT_UI, FONT_DISPLAY, FONT_MONO
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        families = set()

    def pick(options, fallback):
        for name in options:
            if name in families:
                return name
        return fallback

    FONT_UI = pick(("Segoe UI Variable Text", "Segoe UI"), "Segoe UI")
    FONT_DISPLAY = pick(("Bahnschrift", "Segoe UI Variable Display", "Segoe UI Semibold"), "Segoe UI")
    FONT_MONO = pick(("Cascadia Mono", "Cascadia Code", "Consolas"), "Consolas")


def apply_dark_titlebar(root: tk.Tk) -> None:
    if os.name != "nt":
        return
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        on = ctypes.c_int(1)
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(on), ctypes.sizeof(on)
            )
        # Win11: match the title bar and border colour to the body.
        caption = ctypes.c_int(0x00110D0B)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 35, ctypes.byref(caption), ctypes.sizeof(caption)
        )
        border = ctypes.c_int(0x00231D19)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 34, ctypes.byref(border), ctypes.sizeof(border)
        )
    except Exception:
        pass


def round_rect_points(x1, y1, x2, y2, radius, steps=12):
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = []
    corners = (
        (x2 - radius, y1 + radius, -90),
        (x2 - radius, y2 - radius, 0),
        (x1 + radius, y2 - radius, 90),
        (x1 + radius, y1 + radius, 180),
    )
    for cx, cy, start in corners:
        for index in range(steps + 1):
            angle = math.radians(start + 90 * index / steps)
            points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


class Card(tk.Canvas):
    """Rounded panel; content goes into .body."""

    def __init__(self, master, padding=18, radius=14, fill=C.panel, bg=C.bg,
                 border=C.line, stretch=False, **kwargs):
        self.fill = fill
        self.pad = px(padding)
        self.radius = px(radius)
        self.stretch = stretch
        self.border = border
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, **kwargs)
        self.body = tk.Frame(self, bg=fill)
        self._window = self.create_window(self.pad, self.pad, anchor="nw", window=self.body)
        self._shape = None
        self.bind("<Configure>", self._on_resize)
        if not stretch:
            self.body.bind("<Configure>", self._on_body)

    def _on_resize(self, event):
        width = max(2, event.width)
        height = max(2, event.height)
        if self._shape:
            self.delete(self._shape)
        self._shape = self.create_polygon(
            round_rect_points(0.5, 0.5, width - 0.5, height - 0.5, self.radius),
            fill=self.fill,
            outline=self.border,
            width=1,
        )
        self.tag_lower(self._shape)
        self.itemconfigure(self._window, width=max(1, width - 2 * self.pad))
        if self.stretch:
            self.itemconfigure(self._window, height=max(1, height - 2 * self.pad))

    def _on_body(self, _event=None):
        if self.stretch:
            return
        wanted = self.body.winfo_reqheight() + 2 * self.pad
        if abs(int(self.cget("height")) - wanted) > 1:
            self.configure(height=wanted)


class Btn(tk.Canvas):
    STYLES = {
        "primary": (C.lime, C.lime_hi, C.lime_lo, "#0A0C05", C.lime),
        "secondary": (C.panel2, C.panel3, C.panel3, C.text, C.line2),
        "ghost": (C.panel, C.panel2, C.panel2, C.muted, C.panel),
        "danger": ("#1F0E10", "#2A1417", "#2A1417", "#FF9B9B", "#3B1A1F"),
    }

    def __init__(self, master, text="", command=None, variant="primary", bg=None,
                 width=None, height=34, radius=9, font_size=9, family=None):
        self.bg = bg or C.panel
        super().__init__(master, bg=self.bg, highlightthickness=0, bd=0,
                         width=px(width or 90), height=px(height))
        self.command = command
        self.variant = variant
        self.h = px(height)
        self.radius = px(radius)
        self.text = text
        self.enabled = True
        self._hover = False
        self._press = False
        self._fixed_width = px(width) if width else None
        self._font = tkfont.Font(family=family or FONT_UI, size=font_size, weight="bold")
        self._width = self._fixed_width or max(px(40), self._font.measure(text) + px(30))
        self.configure(width=self._width, height=self.h, cursor="hand2")
        for event, handler in (
            ("<Enter>", self._on_enter),
            ("<Leave>", self._on_leave),
            ("<ButtonPress-1>", self._on_press),
            ("<ButtonRelease-1>", self._on_release),
            ("<Configure>", self._on_configure),
        ):
            self.bind(event, handler)
        self._render()

    def _on_enter(self, _event=None):
        self._hover = True
        self._render()

    def _on_leave(self, _event=None):
        self._hover = False
        self._press = False
        self._render()

    def _on_press(self, _event=None):
        self._press = True
        self._render()

    def _on_release(self, event=None):
        was_press = self._press
        self._press = False
        self._render()
        if not was_press or not self.enabled or not self.command:
            return
        if event is not None:
            if not (0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.h):
                return
        self.command()

    def _on_configure(self, _event=None):
        self._render()

    def _render(self):
        self.delete("all")
        fill, hover, press, fg, border = self.STYLES.get(self.variant, self.STYLES["secondary"])
        if not self.enabled:
            fill, fg, border = self.bg, C.dim, C.line
        elif self._press:
            fill = press
        elif self._hover:
            fill = hover
        width = self.winfo_width() or self._width
        self.create_polygon(
            round_rect_points(0.5, 0.5, width - 0.5, self.h - 0.5, self.radius),
            fill=fill, outline=border, width=1,
        )
        self.create_text(width / 2, self.h / 2, text=self.text, fill=fg, font=self._font)

    def set_text(self, text):
        self.text = text
        if self._fixed_width is None:
            self._width = max(px(40), self._font.measure(text) + px(30))
            self.configure(width=self._width)
        self._render()

    def set_variant(self, variant):
        self.variant = variant
        self._render()

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self._render()


class Pill(tk.Canvas):
    TONES = {
        "ok": (C.green, "#0D2118"),
        "run": (C.lime, "#1B2408"),
        "idle": (C.muted, "#14171C"),
        "warn": (C.amber, "#241C0B"),
        "err": (C.red, "#240F11"),
    }

    def __init__(self, master, text="", tone="idle", bg=None, height=24):
        self.bg = bg or C.bg
        self.h = px(height)
        super().__init__(master, bg=self.bg, highlightthickness=0, bd=0, height=self.h)
        self._font = tkfont.Font(family=FONT_UI, size=7, weight="bold")
        self.text = text
        self.tone = tone
        self._width = px(70)
        self._render()

    def set(self, text, tone="idle"):
        self.text = text
        self.tone = tone
        self._render()

    def _render(self):
        self.delete("all")
        color, fill = self.TONES.get(self.tone, self.TONES["idle"])
        width = self._font.measure(self.text) + px(34)
        self._width = width
        self.configure(width=width, height=self.h)
        self.create_polygon(
            round_rect_points(0.5, 0.5, width - 0.5, self.h - 0.5, self.h / 2),
            fill=fill, outline=color, width=1,
        )
        cy = self.h / 2
        self.create_oval(px(10), cy - px(2.5), px(15), cy + px(2.5), fill=color, outline=color)
        self.create_text(px(21), cy, text=self.text, anchor="w", fill=color, font=self._font)


class Ring(tk.Canvas):
    """Orbital gauge: 72-tick dial, progress arc and end dot."""

    def __init__(self, master, size=190, bg=C.panel):
        side = px(size)
        super().__init__(master, width=side, height=side, bg=bg, highlightthickness=0, bd=0)
        self.side = side
        self.frac = 0.0
        self.main = "—"
        self.sub = t("state.ready").lower()
        self.color = C.muted
        self._arc = None
        self._track = None
        self._dot = None
        self._main = None
        self._sub = None
        self._build()

    def _build(self):
        s = self.side
        c = s / 2
        tick_outer = c - px(2)
        for index in range(72):
            angle = math.radians(index * 5 - 90)
            major = index % 6 == 0
            inner = tick_outer - (px(8) if major else px(4))
            self.create_line(
                c + inner * math.cos(angle), c + inner * math.sin(angle),
                c + tick_outer * math.cos(angle), c + tick_outer * math.sin(angle),
                fill=C.line2 if major else C.line, width=px(1),
            )
        radius = c - px(26)
        box = (c - radius, c - radius, c + radius, c + radius)
        self._track = self.create_arc(
            *box, start=0, extent=359.99, style="arc", outline="#171A1F", width=px(7)
        )
        self._arc = self.create_arc(
            *box, start=90, extent=-0.01, style="arc", outline=self.color, width=px(7)
        )
        self._dot = self.create_oval(0, 0, 0, 0, fill=self.color, outline=self.color,
                                     state="hidden")
        self.create_line(c, c - radius - px(9), c, c - radius - px(3),
                         fill=C.line2, width=px(1.4))
        self._main = self.create_text(
            c, c - px(4), text=self.main, fill=C.text,
            font=(FONT_MONO, 21, "bold"),
        )
        self._sub = self.create_text(
            c, c + px(20), text=self.sub, fill=C.dim, font=(FONT_UI, 7)
        )

    def set(self, frac: float, main: str, sub: str, color: str | None = None):
        frac = max(0.0, min(1.0, frac))
        color = color or self.color
        if (abs(self.frac - frac) < 0.0008 and main == self.main
                and sub == self.sub and color == self.color):
            return
        self.frac = frac
        self.main = main
        self.sub = sub
        self.color = color
        self.itemconfigure(self._main, text=main)
        self.itemconfigure(self._sub, text=sub)
        if frac > 0.002:
            self.itemconfigure(self._arc, extent=-359.99 * frac, outline=color,
                               state="normal")
            self.itemconfigure(self._track, outline="#222913")
            angle = math.radians(90 - 360 * frac)
            radius = self.side / 2 - px(26)
            x = self.side / 2 + radius * math.cos(angle)
            y = self.side / 2 - radius * math.sin(angle)
            r = px(4.2)
            self.coords(self._dot, x - r, y - r, x + r, y + r)
            self.itemconfigure(self._dot, fill=color, outline=color, state="normal")
        else:
            self.itemconfigure(self._arc, extent=-0.01, state="hidden")
            self.itemconfigure(self._track, outline="#171A1F")
            self.itemconfigure(self._dot, state="hidden")


class IpView(tk.Canvas):
    """Large IP display: last octet highlighted, click to copy."""

    def __init__(self, master, bg=C.panel, size=26, on_click=None):
        self.font = tkfont.Font(family=FONT_MONO, size=size, weight="bold")
        width = self.font.measure("000.000.000.000") + px(6)
        height = px(size * 1.75)
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=width, height=height, cursor="hand2")
        self._ip = ""
        self._on_click = on_click
        self._height = height
        self._prefix = self.create_text(
            0, height / 2, anchor="w", text="—. —. —. —", fill=C.line2, font=self.font
        )
        self._tail = self.create_text(
            0, height / 2, anchor="w", text="", fill=C.lime, font=self.font
        )
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", lambda _e: self._place_tail())

    def _place_tail(self, _event=None):
        if not self._ip:
            return
        cut = self._ip.rfind(".")
        if cut < 0:
            return
        self.coords(self._tail, self.font.measure(self._ip[: cut + 1]),
                    self.winfo_height() / 2)

    def _click(self, _event=None):
        if self._on_click and self._ip:
            self._on_click(self._ip)

    def set_ip(self, ip: str):
        self._ip = ip or ""
        if not ip:
            self.itemconfigure(self._prefix, text="—. —. —. —", fill=C.line2)
            self.itemconfigure(self._tail, text="")
            return
        cut = ip.rfind(".")
        if cut < 0:
            self.itemconfigure(self._prefix, text=ip, fill=C.text)
            self.itemconfigure(self._tail, text="")
            return
        prefix, tail = ip[: cut + 1], ip[cut + 1:]
        self.itemconfigure(self._prefix, text=prefix, fill=C.text)
        self.itemconfigure(self._tail, text=tail, fill=C.lime)
        self.coords(self._tail, self.font.measure(prefix),
                    (self.winfo_height() or self._height) / 2)


class Spark(tk.Canvas):
    """Duration bars of recent cycles: lime = IP changed, amber = unchanged."""

    def __init__(self, master, width=150, height=44, bg=C.panel):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=px(width), height=px(height))
        self.w = px(width)
        self.h = px(height)
        self.bars: list[tuple[bool, float]] = []
        self.bind("<Configure>", lambda _e: self._render())

    def push(self, changed: bool, seconds: float):
        self.bars.append((bool(changed), max(0.0, float(seconds))))
        if len(self.bars) > 18:
            self.bars.pop(0)
        self._render()

    def _render(self):
        self.delete("all")
        width = self.winfo_width() or self.w
        height = self.h
        baseline = height - px(4)
        self.create_line(0, baseline, width, baseline, fill=C.line)
        if not self.bars:
            self.create_text(
                width / 2, height / 2 - px(2), text=t("stats.waiting"),
                fill=C.dim, font=(FONT_UI, 7),
            )
            return
        count = len(self.bars)
        slot = width / 18
        bar_w = max(px(3), slot - px(4))
        peak = max(seconds for _, seconds in self.bars) or 1.0
        for index, (changed, seconds) in enumerate(self.bars):
            x = index * slot + (slot - bar_w) / 2
            bar_h = max(px(4), (baseline - px(6)) * min(1.0, seconds / peak))
            color = C.lime if changed else C.amber
            if index == count - 1:
                color = C.lime_hi if changed else C.amber
            self.create_rectangle(
                x, baseline - bar_h, x + bar_w, baseline,
                fill=color, outline="",
            )


class Segmented(tk.Canvas):
    def __init__(self, master, options, value, on_change, bg=C.panel,
                 width=200, height=28, font_size=8):
        self.options = list(options)
        self.value = value
        self.on_change = on_change
        self.h = px(height)
        self._font = tkfont.Font(family=FONT_MONO, size=font_size, weight="bold")
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=px(width), height=self.h, cursor="hand2")
        self.bind("<Button-1>", self._click)
        self.bind("<Configure>", lambda _e: self._render())
        self._render()

    def set_value(self, value):
        if str(value) != str(self.value):
            self.value = value
            self._render()

    def _click(self, event):
        count = max(1, len(self.options))
        width = self.winfo_width()
        cell = (width - px(4)) / count
        index = int(max(0, min(count - 1, (event.x - px(2)) // cell)))
        value = self.options[index]
        if str(value) != str(self.value):
            self.value = value
            self._render()
            if self.on_change:
                self.on_change(value)

    def _render(self):
        self.delete("all")
        width = self.winfo_width() or px(200)
        self.create_polygon(
            round_rect_points(0.5, 0.5, width - 0.5, self.h - 0.5, px(8)),
            fill=C.input, outline=C.line, width=1,
        )
        count = max(1, len(self.options))
        cell = (width - px(4)) / count
        for index, option in enumerate(self.options):
            x1 = px(2) + index * cell
            x2 = x1 + cell
            selected = str(option) == str(self.value)
            if selected:
                self.create_polygon(
                    round_rect_points(x1 + 1, px(2.5), x2 - 1, self.h - px(2.5), px(6)),
                    fill=C.lime, outline=C.lime, width=1,
                )
            self.create_text(
                (x1 + x2) / 2, self.h / 2, text=str(option),
                fill="#0A0C05" if selected else C.dim, font=self._font,
            )


class Stepper(tk.Frame):
    """Numeric stepper. Click the value to type an exact number."""

    def __init__(self, master, value, minimum, maximum, step, on_change,
                 bg=C.panel, unit="dk", decimals=0):
        super().__init__(master, bg=bg)
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.on_change = on_change
        self.decimals = decimals
        self.value = self._clamp(value)
        self.unit = unit
        self.minus = Btn(self, "−", self._dec, "secondary", bg=bg,
                         width=28, height=28, radius=8, font_size=10)
        self.minus.pack(side="left")
        self.label = tk.Label(self, text=self.text, bg=bg, fg=C.text,
                              font=(FONT_MONO, 11, "bold"), width=5, cursor="xterm")
        self.label.pack(side="left")
        self.label.bind("<Button-1>", self._begin_edit)
        self.plus = Btn(self, "+", self._inc, "secondary", bg=bg,
                        width=28, height=28, radius=8, font_size=10)
        self.plus.pack(side="left")
        tk.Label(self, text=unit, bg=bg, fg=C.dim, font=(FONT_UI, 7)).pack(
            side="left", padx=(px(7), 0)
        )

    @property
    def text(self) -> str:
        if self.decimals <= 0:
            return str(int(round(self.value)))
        text = f"{self.value:.{self.decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    def _clamp(self, value) -> float:
        try:
            number = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            number = self.minimum
        number = round(number, self.decimals)
        return max(self.minimum, min(self.maximum, number))

    def _render(self) -> None:
        self.label.configure(text=self.text)

    def _apply(self, value):
        value = self._clamp(value)
        if abs(value - self.value) < 1e-9:
            return
        self.value = value
        self._render()
        if self.on_change:
            self.on_change(value)

    def _dec(self):
        self._apply(self.value - self.step)

    def _inc(self):
        self._apply(self.value + self.step)

    def set_value(self, value):
        self.value = self._clamp(value)
        self._render()

    def _begin_edit(self, _event=None):
        entry = tk.Entry(
            self, bg=C.input, fg=C.text, insertbackground=C.lime,
            relief="flat", justify="center", width=5,
            font=(FONT_MONO, 11, "bold"), highlightthickness=1,
            highlightbackground=C.lime, highlightcolor=C.lime,
        )
        entry.insert(0, self.text)
        entry.select_range(0, "end")
        self.label.pack_forget()
        entry.pack(side="left", before=self.plus)
        entry.focus_set()

        def commit(_event=None):
            self._apply(entry.get())
            self._end_edit(entry)

        def cancel(_event=None):
            self._end_edit(entry)

        entry.bind("<Return>", commit)
        entry.bind("<KP_Enter>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", cancel)

    def _end_edit(self, entry: tk.Entry) -> None:
        try:
            entry.destroy()
        except tk.TclError:
            pass
        self.label.pack(side="left", before=self.plus)


class Select(tk.Canvas):
    """Dark themed dropdown list."""

    def __init__(self, master, values, textvariable, bg=C.panel, height=32):
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=px(height))
        self.values = list(values)
        self.var = textvariable
        self.h = px(height)
        self._font = tkfont.Font(family=FONT_UI, size=9)
        self._popup = None
        self._hover = False
        self.bind("<Button-1>", self._toggle)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<Configure>", lambda _e: self._render())
        self.var.trace_add("write", lambda *_a: self._render())
        self.configure(cursor="hand2")
        self._render()

    def set_values(self, values):
        self.values = list(values)
        if self.var.get() not in self.values and self.values:
            self.var.set(self.values[0])

    def _set_hover(self, flag):
        self._hover = flag
        self._render()

    def _render(self):
        self.delete("all")
        width = self.winfo_width() or px(200)
        border = C.lime if (self._hover or self._popup) else C.line2
        self.create_polygon(
            round_rect_points(0.5, 0.5, width - 0.5, self.h - 0.5, px(8)),
            fill=C.input, outline=border, width=1,
        )
        text = self.var.get() or t("select.connection")
        color = C.text if self.var.get() else C.dim
        self.create_text(px(11), self.h / 2, anchor="w", text=text,
                         fill=color, font=self._font)
        right = width - px(13)
        self.create_line(right - px(4), self.h / 2 - px(2), right, self.h / 2 + px(2),
                         right + px(4), self.h / 2 - px(2), fill=C.muted, width=px(1.6))

    def _toggle(self, _event=None):
        if self._popup:
            self._close()
            return
        if not self.values:
            return
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=C.line2)
        popup.attributes("-topmost", True)
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + px(4)
        width = max(px(200), self.winfo_width())
        row_height = px(30)
        height = min(len(self.values), 8) * row_height + px(2)
        popup.geometry(f"{width}x{height}+{x}+{y}")
        frame = tk.Frame(popup, bg=C.panel2)
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        for value in self.values:
            row = tk.Label(frame, text=value, bg=C.panel2, fg=C.text, anchor="w",
                           padx=px(11), pady=px(5), font=(FONT_UI, 9))
            row.pack(fill="x")
            row.bind("<Enter>", lambda _e, w=row: w.configure(bg=C.panel3))
            row.bind("<Leave>", lambda _e, w=row: w.configure(bg=C.panel2))
            row.bind("<Button-1>", lambda _e, v=value: self._choose(v))
        popup.bind("<Escape>", lambda _e: self._close())
        popup.bind("<FocusOut>", lambda _e: self._close())
        popup.after(30, popup.focus_force)
        self._popup = popup
        self._render()

    def _choose(self, value):
        self.var.set(value)
        self._close()

    def _close(self):
        if self._popup:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
            self._popup = None
        self._render()


class ThinScroll(tk.Canvas):
    """Thin dark scrollbar (replaces the white Windows one)."""

    def __init__(self, master, command, bg=C.input, width=7):
        self.w = px(width)
        super().__init__(master, bg=bg, highlightthickness=0, bd=0,
                         width=self.w, height=px(40))
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self._drag_offset = None
        self.bind("<Configure>", lambda _e: self._render())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag_offset", None))

    def set(self, first, last):
        self.first = float(first)
        self.last = float(last)
        self._render()

    def _geometry(self):
        height = self.winfo_height()
        top = height * self.first
        bottom = max(top + px(24), height * self.last)
        return height, top, min(bottom, height)

    def _render(self):
        self.delete("all")
        height = self.winfo_height()
        width = self.winfo_width()
        if height < 8:
            return
        self.create_rectangle(0, 0, width, height, fill=C.panel2, outline="")
        if self.last - self.first >= 0.999:
            return
        _, top, bottom = self._geometry()
        self.create_rectangle(px(1.5), top + px(2), width - px(1.5), bottom - px(2),
                              fill=C.line2, outline="")

    def _on_press(self, event):
        _, top, bottom = self._geometry()
        if top <= event.y <= bottom:
            self._drag_offset = event.y - top
            return
        self._drag_offset = (bottom - top) / 2
        self._scroll_to(event.y)

    def _on_drag(self, event):
        if self._drag_offset is None:
            return
        self._scroll_to(event.y)

    def _scroll_to(self, y):
        height = max(1, self.winfo_height())
        span = max(0.02, self.last - self.first)
        fraction = (y - (self._drag_offset or 0)) / height
        fraction = max(0.0, min(1.0 - span, fraction))
        self.command("moveto", fraction)


class App:
    def __init__(self, root: tk.Tk, check_updates: bool = True, demo: bool = False):
        global LANG
        self.root = root
        self.settings = load_settings()
        self.queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.running = False
        self.busy = False
        self.stopping = False
        self.auth_failed = False
        self.next_run: float | None = None
        self.interval_sec = max(3.0, float(self.settings.interval_sec))
        self.cycles = 0
        self.run_started: float | None = None
        self.cycle_started: float | None = None
        self.last_ip = ""
        self.last_change: float | None = None
        self.update_info: UpdateInfo | None = None
        self.update_busy = False
        self._check_on_start = check_updates
        self._installing = False
        self._update_checked = False
        self._toast_label: tk.Label | None = None
        self.status_text = t("status.idle")
        self.status_tone = "idle"
        self.status_color = C.muted
        self.log_history: list[tuple[str, str, str]] = []
        self.shell: tk.Frame | None = None

        LANG = FORCED_LANG or (
            self.settings.language if self.settings.language in ("tr", "en") else "en"
        )

        init_scale(root)
        setup_fonts(root)
        self._build_ui()
        self._load_settings_into_ui()
        self.root.report_callback_exception = self._tk_exception
        self.root.after(120, self._drain_queue)
        self.root.after(120, self._tick)
        if self._check_on_start:
            self.root.after(1600, self._auto_check_updates)

        self._log("info", t("log.ready", app=APP_NAME, version=APP_VERSION))
        self._log("dim", t("log.tip"))
        if self.settings.has_password():
            self._log("dim", t("log.saved_password"))
        if demo:
            self._demo_state()

    # -- kurulum ------------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.title(f"{APP_NAME} — TP-Link TD-W9970")
        self.root.configure(bg=C.bg)
        self.root.geometry(f"{px(1140)}x{px(760)}")
        self.root.minsize(px(1040), px(700))
        try:
            icon = APP_DIR / "wan_ip.ico"
            if icon.exists():
                self.root.iconbitmap(default=str(icon))
        except Exception:
            pass
        apply_dark_titlebar(self.root)

        self.shell = shell = tk.Frame(self.root, bg=C.bg)
        shell.pack(fill="both", expand=True, padx=px(18), pady=(px(14), px(12)))

        self._build_header(shell)

        body = tk.Frame(shell, bg=C.bg)
        body.pack(fill="both", expand=True, pady=(px(14), 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=px(360))
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=C.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, px(14)))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        right = tk.Frame(body, bg=C.bg)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        self._build_core(left)
        self._build_stats(left)
        self._build_log(left)
        self._build_connection(right)
        self._build_timing(right)
        self._build_update(right)
        self._build_footer(shell)
        self._update_buttons()

    def _build_header(self, parent) -> None:
        header = tk.Frame(parent, bg=C.bg, height=px(44))
        header.pack(fill="x")
        header.pack_propagate(False)

        mark = tk.Canvas(header, width=px(38), height=px(38), bg=C.bg,
                         highlightthickness=0, bd=0)
        mark.pack(side="left", pady=px(3))
        size = px(38)
        mark.create_polygon(
            round_rect_points(0.5, 0.5, size - 0.5, size - 0.5, px(11)),
            fill=C.panel2, outline=C.line2, width=1,
        )
        inset = px(9)
        box = (inset, inset, size - inset, size - inset)
        mark.create_oval(box, outline=C.line2, width=px(2.2))
        mark.create_arc(*box, start=35, extent=290, style="arc",
                        outline=C.lime, width=px(2.6))
        radius = (size - 2 * inset) / 2
        angle = math.radians(35)
        dot_x = size / 2 + radius * math.cos(angle)
        dot_y = size / 2 - radius * math.sin(angle)
        mark.create_oval(dot_x - px(2.4), dot_y - px(2.4), dot_x + px(2.4), dot_y + px(2.4),
                         fill=C.lime, outline=C.lime)

        titles = tk.Frame(header, bg=C.bg)
        titles.pack(side="left", padx=(px(11), 0), pady=px(3))
        row = tk.Frame(titles, bg=C.bg)
        row.pack(anchor="w")
        tk.Label(row, text="WAN", bg=C.bg, fg=C.text,
                 font=(FONT_DISPLAY, 15, "bold")).pack(side="left")
        tk.Label(row, text="IP", bg=C.bg, fg=C.lime,
                 font=(FONT_DISPLAY, 15, "bold")).pack(side="left", padx=(px(5), 0))
        tk.Label(row, text=t("brand.suffix"), bg=C.bg, fg=C.dim,
                 font=(FONT_UI, 7, "bold")).pack(side="left", padx=(px(9), 0), pady=(px(4), 0))
        tk.Label(titles, text=t("app.tagline"),
                 bg=C.bg, fg=C.dim, font=(FONT_UI, 8)).pack(anchor="w", pady=(px(1), 0))

        side = tk.Frame(header, bg=C.bg)
        side.pack(side="right", pady=px(8))
        self.status_badge = Pill(side, t("state.ready"), "ok", bg=C.bg)
        self.status_badge.pack(side="right")
        self.version_badge = Pill(side, f"v{APP_VERSION}", "idle", bg=C.bg)
        self.version_badge.pack(side="right", padx=(0, px(8)))
        self.lang_switch = Segmented(
            side, ["EN", "TR"], LANG.upper(), self._switch_lang,
            bg=C.bg, width=70, height=24, font_size=7,
        )
        self.lang_switch.pack(side="right", padx=(0, px(8)))

    def _panel_head(self, body, fill, title, hint="") -> tk.Frame:
        row = tk.Frame(body, bg=fill)
        row.pack(fill="x", pady=(0, px(10)))
        tk.Label(row, text=title, bg=fill, fg=C.text,
                 font=(FONT_DISPLAY, 10, "bold")).pack(side="left")
        if hint:
            tk.Label(row, text=hint, bg=fill, fg=C.dim,
                     font=(FONT_UI, 7)).pack(side="left", padx=(px(8), 0), pady=(px(2), 0))
        return row

    def _field_label(self, parent, text: str) -> tk.Label:
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=C.dim,
                        font=(FONT_UI, 7, "bold"))

    def _entry(self, parent) -> tk.Entry:
        return tk.Entry(
            parent, bg=C.input, fg=C.text, insertbackground=C.lime,
            relief="flat", bd=0, highlightthickness=1,
            highlightbackground=C.line2, highlightcolor=C.lime,
            font=(FONT_UI, 9), disabledbackground=C.input,
            disabledforeground=C.dim,
        )

    def _build_core(self, parent) -> None:
        card = Card(parent, padding=20)
        card.grid(row=0, column=0, sticky="ew")
        body = card.body
        body.columnconfigure(1, weight=1)

        self.gauge = Ring(body, size=190, bg=card.fill)
        self.gauge.grid(row=0, column=0, rowspan=5, padx=(0, px(24)))

        head = tk.Frame(body, bg=card.fill)
        head.grid(row=0, column=1, sticky="w")
        dot = tk.Canvas(head, width=px(7), height=px(7), bg=card.fill,
                        highlightthickness=0, bd=0)
        dot.pack(side="left", padx=(0, px(6)))
        dot.create_oval(0, 0, px(7), px(7), fill=C.lime, outline=C.lime)
        tk.Label(head, text=t("core.ip_label"), bg=card.fill, fg=C.muted,
                 font=(FONT_UI, 7, "bold")).pack(side="left")

        self.ip_view = IpView(body, bg=card.fill, size=26, on_click=self._copy_ip)
        self.ip_view.grid(row=1, column=1, sticky="w", pady=(px(2), 0))

        self.ip_hint = tk.Label(body, text=t("core.hint_empty"),
                                bg=card.fill, fg=C.dim, font=(FONT_UI, 8))
        self.ip_hint.grid(row=2, column=1, sticky="w")

        actions = tk.Frame(body, bg=card.fill)
        actions.grid(row=3, column=1, sticky="w", pady=(px(16), 0))
        self.start_btn = Btn(actions, t("btn.start"), self.on_start, "primary",
                             bg=card.fill, width=118, height=36)
        self.start_btn.pack(side="left")
        self.stop_btn = Btn(actions, t("btn.stop"), self.on_stop, "secondary",
                            bg=card.fill, width=100, height=36)
        self.stop_btn.pack(side="left", padx=(px(8), 0))
        self.once_btn = Btn(actions, t("btn.once"), self.on_once, "ghost",
                            bg=card.fill, width=96, height=36)
        self.once_btn.pack(side="left", padx=(px(8), 0))

        self.meta = tk.Label(body, text="", bg=card.fill, fg=C.dim,
                             font=(FONT_UI, 7))
        self.meta.grid(row=4, column=1, sticky="w", pady=(px(12), 0))

    def _stat_block(self, parent, column: int, title: str, value: str) -> tk.Label:
        fill = parent.cget("bg")
        block = tk.Frame(parent, bg=fill)
        block.grid(row=0, column=column, sticky="nsew")
        tk.Label(block, text=title, bg=fill, fg=C.dim,
                 font=(FONT_UI, 7, "bold")).pack(anchor="w")
        label = tk.Label(block, text=value, bg=fill, fg=C.text,
                         font=(FONT_MONO, 12, "bold"))
        label.pack(anchor="w", pady=(px(3), 0))
        return label

    def _divider(self, parent, column: int) -> None:
        tk.Frame(parent, bg=C.line, width=1).grid(row=0, column=column, sticky="ns", padx=px(14))

    def _build_stats(self, parent) -> None:
        card = Card(parent, padding=16)
        card.grid(row=1, column=0, sticky="ew", pady=(px(12), 0))
        body = card.body
        body.columnconfigure(5, weight=1)

        for column in (0, 2, 4):
            body.columnconfigure(column, weight=0, uniform="stat")
        self.cycles_label = self._stat_block(body, 0, t("stats.cycles"), "0")
        self._divider(body, 1)
        self.change_label = self._stat_block(body, 2, t("stats.last_change"), "—")
        self._divider(body, 3)
        self.uptime_label = self._stat_block(body, 4, t("stats.uptime"), "—")

        spark_box = tk.Frame(body, bg=card.fill)
        spark_box.grid(row=0, column=5, sticky="e")
        tk.Label(spark_box, text=t("stats.recent"), bg=card.fill, fg=C.dim,
                 font=(FONT_UI, 7, "bold")).pack(anchor="e")
        self.spark = Spark(spark_box, width=150, height=34, bg=card.fill)
        self.spark.pack(anchor="e", pady=(px(3), 0))

    def _build_log(self, parent) -> None:
        card = Card(parent, padding=16, stretch=True)
        card.grid(row=2, column=0, sticky="nsew", pady=(px(12), 0))
        body = card.body

        head = tk.Frame(body, bg=card.fill)
        head.pack(fill="x", pady=(0, px(8)))
        tk.Label(head, text=t("log.title"), bg=card.fill, fg=C.text,
                 font=(FONT_DISPLAY, 10, "bold")).pack(side="left")
        tk.Label(head, text=t("log.hint"), bg=card.fill, fg=C.dim,
                 font=(FONT_UI, 7)).pack(side="left", padx=(px(8), 0), pady=(px(2), 0))
        Btn(head, t("btn.file"), self.on_open_log, "ghost", bg=card.fill,
            height=26, font_size=8).pack(side="right")
        Btn(head, t("btn.clear"), self.on_clear_log, "ghost", bg=card.fill,
            height=26, font_size=8).pack(side="right", padx=(0, px(4)))

        console = tk.Frame(body, bg=C.input, highlightthickness=1,
                           highlightbackground=C.line)
        console.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            console, bg=C.input, fg="#C6CFDB", bd=0, highlightthickness=0,
            wrap="word", font=(FONT_MONO, 8), padx=px(10), pady=px(8),
            insertbackground=C.lime, selectbackground=C.line2,
            width=20, height=5,
        )
        self.log_scroll = ThinScroll(console, self.log_text.yview, bg=C.input, width=7)
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        self.log_scroll.pack(side="right", fill="y", padx=(px(5), px(2)))
        self.log_text.pack(side="left", fill="both", expand=True)

        self.log_text.tag_configure("ts", foreground=C.dim)
        self.log_text.tag_configure("info", foreground="#C6CFDB")
        self.log_text.tag_configure("dim", foreground=C.dim)
        self.log_text.tag_configure("success", foreground=C.green)
        self.log_text.tag_configure("warn", foreground=C.amber)
        self.log_text.tag_configure("error", foreground=C.red)
        self.log_text.configure(state="disabled")

    def _build_connection(self, parent) -> None:
        card = Card(parent, padding=16)
        card.grid(row=0, column=0, sticky="ew")
        body = card.body
        fill = card.fill
        self._panel_head(body, fill, t("conn.title"), t("conn.hint"))

        pair = tk.Frame(body, bg=fill)
        pair.pack(fill="x", pady=(0, px(6)))
        pair.columnconfigure(0, weight=1, uniform="pair")
        pair.columnconfigure(1, weight=1, uniform="pair")

        host_col = tk.Frame(pair, bg=fill)
        host_col.grid(row=0, column=0, sticky="ew", padx=(0, px(5)))
        self._field_label(host_col, t("conn.host")).pack(anchor="w")
        self.host_var = tk.StringVar()
        self.host_entry = self._entry(host_col)
        self.host_entry.configure(textvariable=self.host_var)
        self.host_entry.pack(fill="x", ipady=px(4), pady=(px(3), 0))

        user_col = tk.Frame(pair, bg=fill)
        user_col.grid(row=0, column=1, sticky="ew", padx=(px(5), 0))
        self._field_label(user_col, t("conn.user")).pack(anchor="w")
        self.user_var = tk.StringVar()
        self.user_entry = self._entry(user_col)
        self.user_entry.configure(textvariable=self.user_var)
        self.user_entry.pack(fill="x", ipady=px(4), pady=(px(3), 0))

        self._field_label(body, t("conn.pass")).pack(anchor="w")
        password_row = tk.Frame(body, bg=fill)
        password_row.pack(fill="x", pady=(px(3), px(8)))
        self.pass_var = tk.StringVar()
        self.pass_entry = self._entry(password_row)
        self.pass_entry.configure(textvariable=self.pass_var, show="•")
        self.pass_entry.pack(side="left", fill="x", expand=True, ipady=px(4))
        self.pass_btn = Btn(password_row, t("btn.show"), self._toggle_pass, "secondary",
                            bg=fill, width=62, height=28, font_size=8)
        self.pass_btn.pack(side="left", padx=(px(6), 0))

        self._field_label(body, t("conn.target")).pack(anchor="w")
        target_row = tk.Frame(body, bg=fill)
        target_row.pack(fill="x", pady=(px(3), px(2)))
        self.target_var = tk.StringVar()
        self.target_select = Select(target_row, ["dsl_internet"], self.target_var,
                                    bg=fill, height=32)
        self.target_select.pack(side="left", fill="x", expand=True)
        self.list_btn = Btn(target_row, t("btn.list"), self.on_list, "secondary",
                            bg=fill, width=78, height=32, font_size=8)
        self.list_btn.pack(side="left", padx=(px(6), 0))

        footer = tk.Frame(body, bg=fill)
        footer.pack(fill="x", pady=(px(8), 0))
        tk.Label(footer, text=t("conn.dpapi"), bg=fill, fg=C.dim,
                 font=(FONT_UI, 7)).pack(side="left")
        self.save_btn = Btn(footer, t("btn.save"), self.on_save, "ghost",
                            bg=fill, height=28, font_size=8)
        self.save_btn.pack(side="right")

    def _build_timing(self, parent) -> None:
        card = Card(parent, padding=16)
        card.grid(row=1, column=0, sticky="ew", pady=(px(12), 0))
        body = card.body
        fill = card.fill
        self._panel_head(body, fill, t("timing.title"), t("timing.hint"))

        self.preset = Segmented(
            body, list(TIMING_PRESETS), "",
            self._on_preset, bg=fill, height=26, font_size=8,
        )
        self.preset.pack(fill="x", pady=(0, px(8)))

        gridbox = tk.Frame(body, bg=fill)
        gridbox.pack(fill="x")
        gridbox.columnconfigure(1, weight=1)

        rows = (
            (t("timing.interval"), 0.05, 1440, 0.05, t("unit.min"), "interval", 2),
            (t("timing.gap"), 0, 300, 0.5, t("unit.sec"), "wait", 1),
            (t("timing.timeout"), 5, 600, 5, t("unit.sec"), "timeout", 0),
        )
        self.steppers: dict[str, Stepper] = {}
        for index, (title, low, high, step, unit, key, decimals) in enumerate(rows):
            tk.Label(gridbox, text=title, bg=fill, fg=C.muted,
                     font=(FONT_UI, 8)).grid(row=index, column=0, sticky="w", pady=px(4))
            stepper = Stepper(gridbox, 2, low, high, step, None, bg=fill,
                              unit=unit, decimals=decimals)
            stepper.on_change = self._on_stepper_change
            stepper.grid(row=index, column=1, sticky="e", pady=px(4))
            self.steppers[key] = stepper
        self.steppers["interval"].on_change = self._on_interval_change

    def _build_update(self, parent) -> None:
        card = Card(parent, padding=16)
        card.grid(row=2, column=0, sticky="ew", pady=(px(12), 0))
        body = card.body
        fill = card.fill

        head = self._panel_head(body, fill, t("update.title"))
        tk.Label(head, text=f"v{APP_VERSION}", bg=fill, fg=C.dim,
                 font=(FONT_MONO, 8)).pack(side="right")

        self.update_status = tk.Label(
            body, text=t("update.checking"), bg=fill, fg=C.dim,
            font=(FONT_UI, 8), anchor="w", justify="left", wraplength=px(300),
        )
        self.update_status.pack(fill="x", pady=(0, px(10)))

        actions = tk.Frame(body, bg=fill)
        actions.pack(fill="x")
        self.check_btn = Btn(actions, t("btn.check"), self.on_check_updates, "secondary",
                             bg=fill, width=84, height=30, font_size=8)
        self.check_btn.pack(side="left")
        self.install_btn = Btn(actions, t("btn.install"), self.on_install_update, "primary",
                               bg=fill, width=84, height=30, font_size=8)
        self.install_btn.pack(side="left", padx=(px(6), 0))

        link = tk.Label(actions, text="GitHub ↗", bg=fill, fg=C.muted,
                        font=(FONT_UI, 8), cursor="hand2")
        link.pack(side="right")
        link.bind("<Button-1>", lambda _e: self._open_repo())
        link.bind("<Enter>", lambda _e: link.configure(fg=C.lime))
        link.bind("<Leave>", lambda _e: link.configure(fg=C.muted))

    def _build_footer(self, parent) -> None:
        footer = tk.Frame(parent, bg=C.bg)
        footer.pack(fill="x", pady=(px(10), 0))
        tk.Label(
            footer,
            text=t("footer.left"),
            bg=C.bg, fg=C.dim, font=(FONT_UI, 7),
        ).pack(side="left")
        tk.Label(footer, text=f"v{APP_VERSION}", bg=C.bg, fg=C.dim,
                 font=(FONT_MONO, 7)).pack(side="right")

    # -- settings loading ---------------------------------------------------

    def _demo_state(self) -> None:
        """--demo only: fake state so the UI renders populated."""
        now = time.time()
        self.interval_sec = 19.2
        self.cycles = 12
        self.last_change = now - 8
        self.run_started = now - 3725
        self.running = True
        self.next_run = now + 11
        self.steppers["interval"].set_value(0.32)
        self.steppers["wait"].set_value(2)
        self.steppers["timeout"].set_value(75)
        self.preset.set_value("0.32")
        self._update_meta()
        self._apply_ip("85.104.233.17")
        for changed, seconds in (
            (True, 22), (False, 24), (True, 19), (True, 31), (False, 27),
            (True, 21), (True, 18), (True, 26), (False, 33), (True, 20),
            (True, 23), (True, 19),
        ):
            self.spark.push(changed, seconds)
        self._update_stats()
        self._set_status(t("status.idle"), "run")
        self._update_buttons()
        self.update_status.configure(text=t("update.current", version=APP_VERSION), fg=C.green)
        self._log("info", t("log.started", span=format_span(19.2)))
        self._log(
            "dim",
            t("log.target_line", target="dsl_internet", wait="2", timeout=75),
        )
        self._log("dim", t("log.login_ok"))
        self._log(
            "info",
            t(
                "log.target_state",
                name="dsl_internet",
                state="Connected",
                ip="85.104.233.17",
                stack=0,
            ),
        )
        self._log("info", t("log.disconnected"))
        self._log("info", t("log.reconnect_cmd"))
        self._log("success", t("log.ip_changed", old="78.180.44.9", new="85.104.233.17"))

    def _load_settings_into_ui(self) -> None:
        self.host_var.set(self.settings.host)
        self.user_var.set(self.settings.username)
        self.target_var.set(self.settings.target)
        self.target_select.set_values([self.settings.target or "dsl_internet"])
        minutes = max(0.05, self.settings.interval_sec / 60)
        self.steppers["interval"].set_value(minutes)
        self.steppers["wait"].set_value(self.settings.disconnect_wait)
        self.steppers["timeout"].set_value(self.settings.connect_timeout)
        self._sync_preset()
        self.target_var.trace_add("write", lambda *_a: self._update_meta())
        self._update_meta()

    def _sync_preset(self) -> None:
        text = self.steppers["interval"].text
        self.preset.set_value(text if text in TIMING_PRESETS else "")

    def _on_preset(self, value) -> None:
        try:
            minutes = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return
        self.steppers["interval"].set_value(minutes)
        self._sync_preset()
        self._update_meta()

    def _on_interval_change(self, _value) -> None:
        self._sync_preset()
        self._update_meta()

    def _on_stepper_change(self, _value) -> None:
        self._update_meta()

    def _update_meta(self) -> None:
        if not hasattr(self, "meta"):
            return
        target = self.target_var.get().strip() or t("meta.auto")
        self.meta.configure(
            text=t(
                "meta.line",
                target=target,
                minutes=self.steppers["interval"].text,
                wait=self.steppers["wait"].text,
            )
        )

    def _toggle_pass(self) -> None:
        hidden = self.pass_entry.cget("show") != ""
        self.pass_entry.configure(show="" if hidden else "•")
        self.pass_btn.set_text(t("btn.hide") if hidden else t("btn.show"))

    def _open_repo(self) -> None:
        try:
            webbrowser.open(REPO_URL)
        except Exception:
            pass

    def _copy_ip(self, ip: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(ip)
        except tk.TclError:
            return
        self._toast(t("msg.copied", ip=ip))

    def _toast(self, text: str) -> None:
        if self._toast_label is not None:
            try:
                self._toast_label.destroy()
            except tk.TclError:
                pass
        label = tk.Label(
            self.root, text=text, bg=C.panel3, fg=C.text,
            font=(FONT_UI, 8), padx=px(12), pady=px(6),
            highlightthickness=1, highlightbackground=C.line2,
        )
        label.place(relx=0.5, rely=1.0, anchor="s", y=-px(24))
        self._toast_label = label
        self.root.after(1700, label.destroy)

    # -- status and log -----------------------------------------------------

    def _set_status(self, text: str, tone: str = "run") -> None:
        labels = {
            "ok": t("state.ready"),
            "idle": t("state.stopped"),
            "err": t("state.error"),
            "warn": t("state.warn"),
            "run": t("state.running"),
        }
        colors = {"ok": C.green, "idle": C.muted, "err": C.red,
                  "warn": C.amber, "run": C.lime}
        self.status_text = text
        self.status_tone = tone
        self.status_color = colors.get(tone, C.lime)
        self.status_badge.set(labels.get(tone, t("state.running")), tone)
        self.gauge.set(self.gauge.frac, self.gauge.main, text, self.status_color)

    def _switch_lang(self, value) -> None:
        global LANG
        code = "tr" if str(value).upper() == "TR" else "en"
        if code == LANG:
            return
        LANG = code
        self.settings.language = code
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self._rebuild_ui()

    def _rebuild_ui(self) -> None:
        if self.shell is not None:
            try:
                self.shell.destroy()
            except tk.TclError:
                pass
            self.shell = None
        self._build_ui()
        self._load_settings_into_ui()
        self._replay_log()
        self._update_buttons()
        self._update_stats()
        self._set_status(self.status_text, self.status_tone)
        apply_dark_titlebar(self.root)

    def _replay_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        for stamp, level, message in self.log_history[-400:]:
            self.log_text.insert("end", stamp + "  ", "ts")
            self.log_text.insert("end", message + "\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log(self, level: str, message: str) -> None:
        if level not in ("info", "dim", "success", "warn", "error"):
            level = "info"
        stamp = time.strftime("%H:%M:%S")
        self.log_history.append((stamp, level, message))
        if len(self.log_history) > 600:
            del self.log_history[:200]
        try:
            self.log_text.configure(state="normal")
            self.log_text.insert("end", stamp + "  ", "ts")
            self.log_text.insert("end", message + "\n", level)
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 1600:
                self.log_text.delete("1.0", "400.0")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except tk.TclError:
            pass
        append_file_log(f"{now_text()} [{level.upper()}] {message}")

    def _tk_exception(self, exc_type, value, tb) -> None:
        import traceback

        detail = "".join(traceback.format_exception(exc_type, value, tb))
        try:
            self._log("error", t("log.ui_error", error=value))
        except Exception:
            pass
        append_file_log(detail)

    def _update_buttons(self) -> None:
        idle = not self.running and not self.busy
        self.start_btn.set_enabled(idle)
        self.once_btn.set_enabled(idle)
        self.list_btn.set_enabled(idle)
        self.save_btn.set_enabled(not self.busy)
        self.stop_btn.set_enabled(self.running and not self.stopping)
        self.check_btn.set_enabled(not self.update_busy and not self.busy)
        self.install_btn.set_enabled(
            bool(self.update_info) and not self.update_busy and not self.busy and not self.running
        )

    # -- read / save settings -----------------------------------------------

    def _read_settings_from_ui(self, require_password: bool) -> Settings | None:
        host = normalize_host(self.host_var.get())
        if not host:
            messagebox.showwarning(
                t("msg.missing_info"), t("msg.host_required"),
                parent=self.root,
            )
            return None
        username = self.user_var.get().strip()
        if not username:
            messagebox.showwarning(
                t("msg.missing_info"), t("msg.user_required"),
                parent=self.root,
            )
            return None
        target = self.target_var.get().strip()

        interval_min = max(0.05, min(1440.0, float(self.steppers["interval"].value)))
        wait_sec = max(0.0, min(300.0, float(self.steppers["wait"].value)))
        timeout_sec = max(5, min(600, int(self.steppers["timeout"].value)))

        settings = Settings(
            host=host,
            username=username,
            target=target,
            interval_sec=round(interval_min * 60, 1),
            disconnect_wait=round(wait_sec, 1),
            connect_timeout=timeout_sec,
            password_dpapi=self.settings.password_dpapi,
            password_plain=self.settings.password_plain,
            language=LANG,
        )
        typed_password = self.pass_var.get()
        if typed_password:
            settings.set_password(typed_password)

        if require_password and not settings.has_password():
            messagebox.showwarning(
                t("msg.pass_title"),
                t("msg.pass_required"),
                parent=self.root,
            )
            self.pass_entry.focus_set()
            return None
        return settings

    # -- button actions -----------------------------------------------------

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
                t("msg.settings_title"),
                t("msg.settings_body", path=CONFIG_FILE, error=exc),
                parent=self.root,
            )
            return
        self.settings = settings
        self.interval_sec = settings.interval_sec
        self.cycles = 0
        self.run_started = time.time()
        self.next_run = None
        self.stop_event = threading.Event()
        self.running = True
        self.stopping = False
        self.auth_failed = False
        self._update_buttons()
        self._set_status(t("status.starting"), "run")
        self._update_stats()
        self._log(
            "info",
            t("log.started", span=format_span(settings.interval_sec)),
        )
        self._log(
            "dim",
            t(
                "log.target_line",
                target=settings.target or t("meta.auto"),
                wait=f"{settings.disconnect_wait:g}",
                timeout=settings.connect_timeout,
            ),
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
        self._set_status(t("status.stopping"), "run")
        self._log("info", t("log.stop_requested"))
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
                t("msg.settings_title"),
                t("msg.settings_body", path=CONFIG_FILE, error=exc),
                parent=self.root,
            )
            return
        self.settings = settings
        self.interval_sec = settings.interval_sec
        self.busy = True
        self.auth_failed = False
        self.cycle_started = time.time()
        self._update_buttons()
        self._set_status(t("status.changing_ip"), "run")
        self._log("info", t("log.once_started"))
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
        self._set_status(t("status.reading_links"), "run")
        self._log("info", t("log.list_started"))
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
                t("msg.settings_title"),
                t("msg.settings_body", path=CONFIG_FILE, error=exc),
                parent=self.root,
            )
            return
        self.settings = settings
        self.interval_sec = settings.interval_sec
        self._log("success", t("log.settings_saved"))

    def on_clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def on_open_log(self) -> None:
        if not LOG_FILE.exists():
            messagebox.showinfo(
                t("msg.log_title"), t("msg.log_missing"),
                parent=self.root,
            )
            return
        try:
            os.startfile(str(LOG_FILE))
        except OSError as exc:
            messagebox.showerror(
                t("msg.open_error"), f"{LOG_FILE}\n\n{exc}", parent=self.root
            )

    # -- updates ------------------------------------------------------------

    def _auto_check_updates(self) -> None:
        if self._update_checked:
            return
        self._update_checked = True
        self._start_update_check(silent=True)

    def on_check_updates(self) -> None:
        if self.update_busy:
            return
        self._update_checked = True
        self._start_update_check(silent=False)

    def _start_update_check(self, silent: bool) -> None:
        self.update_busy = True
        self.check_btn.set_enabled(False)
        self.update_status.configure(text=t("update.checking"), fg=C.muted)
        self._update_buttons()
        threading.Thread(
            target=self._update_check_worker, args=(silent,), daemon=True,
            name="wan-ip-update-check",
        ).start()

    def _update_check_worker(self, silent: bool) -> None:
        try:
            info = Updater.check()
            self.queue.put(("update_result", info, silent, None))
        except Exception as exc:
            self.queue.put(("update_result", None, silent, str(exc)))

    def on_install_update(self) -> None:
        if not self.update_info:
            return
        if self.update_busy or self.busy or self.running:
            messagebox.showinfo(
                t("msg.update_title"), t("msg.update_stop_first"),
                parent=self.root,
            )
            return
        self.update_busy = True
        self.install_btn.set_enabled(False)
        self.check_btn.set_enabled(False)
        self.update_status.configure(text=t("update.downloading", percent=0), fg=C.muted)
        threading.Thread(
            target=self._update_download_worker, args=(self.update_info,),
            daemon=True, name="wan-ip-update-download",
        ).start()

    def _update_download_worker(self, info: UpdateInfo) -> None:
        try:
            def progress(done: int, total: int) -> None:
                self.queue.put(("update_progress", done, total))

            path = Updater.download(info, progress)
            Updater.validate(path, info.version)
            self.queue.put(("update_ready", path, info.version, None))
        except Exception as exc:
            self.queue.put(("update_ready", None, None, str(exc)))

    def _install_now(self, path: Path, version: str) -> None:
        if not messagebox.askyesno(
            t("msg.update_title"),
            t("update.install_prompt", version=version),
            parent=self.root,
        ):
            self.update_busy = False
            self.install_btn.set_enabled(True)
            self.check_btn.set_enabled(True)
            self.update_status.configure(text=t("update.cancelled"), fg=C.dim)
            return
        try:
            Updater.install(path)
        except Exception as exc:
            self.update_busy = False
            messagebox.showerror(t("msg.update_error_title"), str(exc), parent=self.root)
            self.update_status.configure(text=t("update.failed_install"), fg=C.red)
            self._update_buttons()
            return
        self._log("success", t("update.installing_log", version=version))
        self._installing = True
        self.root.after(250, self.root.destroy)

    # -- background work ----------------------------------------------------

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
            post(("cycle_start", None))
            post(("status", t("status.changing_ip"), "run"))
            try:
                self._cycle(settings, stop, post)
                if not stop.is_set():
                    post(("status", t("status.idle"), "ok"))
            except AuthError as exc:
                post(("log", "error", str(exc)))
                post(("auth_failed", str(exc)))
                break
            except RouterError as exc:
                post(("log", "error", t("log.cycle_error", error=exc)))
                post(("status", t("status.retry"), "warn"))
            except Exception as exc:  # an unexpected error must not end the loop
                post(("log", "error", t("log.unexpected", error=repr(exc))))
                post(("status", t("status.retry"), "warn"))
        post(("next_run", None))
        post(("loop_end", None))

    def _cycle(self, settings: Settings, stop: threading.Event, post) -> None:
        client = RouterClient(
            settings.host, settings.username, settings.password(), timeout=12
        )
        try:
            post(("status", t("status.logging_in"), "run"))
            client.login()
            post(("log", "dim", t("log.login_ok")))
            if stop.is_set():
                return

            entries = client.list_wan()
            entry = choose_entry(entries, settings.target)
            if entry is None:
                names = ", ".join(e.get("name", "?") for e in entries) or t("err.none")
                raise RouterError(
                    t("err.target_missing", target=settings.target, names=names)
                )

            name = entry.get("name", "?")
            stack = entry["__stack"]
            state = entry.get("connectionStatus", "?")
            old_ip = clean_ip(entry.get("externalIPAddress"))
            post(
                (
                    "log",
                    "info",
                    t(
                        "log.target_state",
                        name=name,
                        state=state,
                        ip=old_ip or t("err.ip_none"),
                        stack=stack,
                    ),
                )
            )
            if old_ip:
                post(("ip", old_ip))
            if stop.is_set():
                return

            if state == "Connected":
                post(("status", t("status.disconnecting", name=name), "run"))
                client.ppp_action("ACT_PPP_DISCONN", stack)
                post(("log", "info", t("log.disconnected")))
                if stop.wait(max(0, settings.disconnect_wait)):
                    post(("log", "warn", t("log.stop_during_gap")))
            else:
                post(("log", "warn", t("log.already_state", state=state)))

            post(("status", t("status.reconnecting", name=name), "run"))
            client.ppp_action("ACT_PPP_CONN", stack)
            post(("log", "info", t("log.reconnect_cmd")))

            deadline = time.time() + max(5, settings.connect_timeout)
            new_ip = ""
            last_state = ""
            stopped_early = False
            while time.time() < deadline:
                entries = client.list_wan()
                current = find_entry(entries, name, stack)
                if current is not None:
                    current_state = current.get("connectionStatus", "")
                    if current_state != last_state:
                        last_state = current_state
                        post(("log", "dim", t("log.state_change", state=current_state or "?")))
                    current_ip = clean_ip(current.get("externalIPAddress"))
                    if current_state == "Connected" and current_ip:
                        new_ip = current_ip
                        break
                if stop.wait(0.75):
                    stopped_early = True
                    break

            if stopped_early:
                post(("log", "warn", t("log.stop_early")))
                post(("status", t("status.stopped"), "idle"))
                return

            if not new_ip:
                post(("log", "warn", t("log.timeout")))
                post(("status", t("status.unverified"), "warn"))
                return

            post(("ip", new_ip))
            post(("cycle_done", old_ip, new_ip))
            post(("status", t("status.done"), "ok"))
            if old_ip and new_ip == old_ip:
                post(("log", "warn", t("log.same_ip", ip=new_ip)))
            elif old_ip:
                post(("log", "success", t("log.ip_changed", old=old_ip, new=new_ip)))
            else:
                post(("log", "success", t("log.connected_ip", ip=new_ip)))
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
            post(("status", t("status.error"), "err"))
        except Exception as exc:
            post(("log", "error", t("log.unexpected", error=repr(exc))))
            post(("status", t("status.error"), "err"))
        finally:
            post(("busy_end", None))

    def _list_worker(self, settings: Settings) -> None:
        client = RouterClient(
            settings.host, settings.username, settings.password(), timeout=12
        )
        post = self.queue.put
        try:
            post(("log", "dim", t("log.signing_in")))
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
            post(("log", "success", t("log.entries", count=len(rows))))
            post(("status", t("status.list_ready"), "ok"))
        except AuthError as exc:
            post(("log", "error", str(exc)))
            post(("auth_failed", str(exc)))
        except RouterError as exc:
            post(("log", "error", str(exc)))
            post(("status", t("status.error"), "err"))
        except Exception as exc:
            post(("log", "error", t("log.unexpected", error=repr(exc))))
            post(("status", t("status.error"), "err"))
        finally:
            try:
                client.logout()
            except Exception:
                pass
            post(("busy_end", None))

    # -- queue / timer ------------------------------------------------------

    def _handle_entries(self, rows: list[dict]) -> None:
        names = [row["name"] for row in rows if row.get("name")]
        self.target_select.set_values(names)
        current = self.target_var.get().strip()
        connected = [
            row for row in rows
            if row.get("status") == "Connected" and row.get("name")
        ]
        if current not in names:
            if len(connected) == 1:
                self.target_var.set(connected[0]["name"])
                self._log("info", t("log.auto_target", name=connected[0]["name"]))
            elif not current and names:
                self.target_var.set(names[0])
        for row in rows:
            self._log(
                "info",
                t(
                    "log.entry_line",
                    name=row["name"],
                    status=row["status"],
                    ip=row["ip"] or t("err.ip_none"),
                    stack=row["stack"],
                ),
            )
        if connected and connected[0].get("ip"):
            self._apply_ip(connected[0]["ip"])

    def _apply_ip(self, ip: str) -> None:
        self.last_ip = ip
        self.ip_view.set_ip(ip)
        if self.last_change:
            self.ip_hint.configure(
                text=t(
                    "core.hint_known",
                    time=time.strftime("%H:%M:%S", time.localtime(self.last_change)),
                )
            )
        else:
            self.ip_hint.configure(text=t("core.hint_read"))

    def _update_stats(self) -> None:
        self.cycles_label.configure(text=str(self.cycles))
        if self.last_change:
            self.change_label.configure(
                text=time.strftime("%H:%M:%S", time.localtime(self.last_change))
            )
        else:
            self.change_label.configure(text="—")
        if self.run_started:
            elapsed = int(max(0, time.time() - self.run_started))
            hours, rest = divmod(elapsed, 3600)
            minutes, seconds = divmod(rest, 60)
            text = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
            self.uptime_label.configure(text=text)
        else:
            self.uptime_label.configure(text="—")

    def _drain_queue(self) -> None:
        try:
            while True:
                message = self.queue.get_nowait()
                kind = message[0]
                if kind == "log":
                    self._log(message[1], message[2])
                elif kind == "cycle_start":
                    self.cycle_started = time.time()
                elif kind == "status":
                    tone = message[2] if len(message) > 2 else "run"
                    self._set_status(message[1], tone)
                elif kind == "ip":
                    self._apply_ip(message[1])
                elif kind == "cycle_done":
                    self.cycles += 1
                    if message[1] != message[2]:
                        self.last_change = time.time()
                    duration = 0.0
                    if self.cycle_started:
                        duration = time.time() - self.cycle_started
                    self.spark.push(bool(message[1]) and message[1] != message[2], duration)
                    self._update_stats()
                elif kind == "next_run":
                    self.next_run = message[1]
                elif kind == "entries":
                    self._handle_entries(message[1])
                elif kind == "auth_failed":
                    self.auth_failed = True
                    self._set_status(t("status.stopped_auth"), "err")
                    messagebox.showerror(t("msg.auth_title"), message[1], parent=self.root)
                elif kind == "loop_end":
                    self.running = False
                    self.stopping = False
                    self.next_run = None
                    if not self.auth_failed:
                        self._set_status(t("status.stopped"), "idle")
                    self.auth_failed = False
                    self._update_buttons()
                elif kind == "busy_end":
                    self.busy = False
                    self.auth_failed = False
                    self._update_buttons()
                elif kind == "update_result":
                    self._handle_update_result(message[1], message[2], message[3])
                elif kind == "update_progress":
                    done, total = message[1], message[2]
                    percent = int(done * 100 / total) if total else 0
                    self.update_status.configure(
                        text=t(
                            "update.downloading_kb",
                            percent=percent,
                            kb=done // 1024,
                        )
                    )
                elif kind == "update_ready":
                    self._handle_update_ready(message[1], message[2], message[3])
        except queue.Empty:
            pass
        self.root.after(120, self._drain_queue)

    def _handle_update_result(self, info, silent: bool, error: str | None) -> None:
        self.update_busy = False
        self.check_btn.set_enabled(True)
        if error:
            self.update_status.configure(text=t("update.failed_check", error=error), fg=C.dim)
            if not silent:
                self._log("warn", t("log.update_check_failed", error=error))
            self._update_buttons()
            return
        if info:
            self.update_info = info
            self.version_badge.set(f"v{APP_VERSION} → v{info.version}", "warn")
            notes = info.notes.strip().splitlines()[0][:90] if info.notes.strip() else ""
            text = t("update.available", version=info.version)
            if notes:
                text += f"\n{notes}"
            self.update_status.configure(text=text, fg=C.amber)
            self.install_btn.set_text(t("update.button", version=info.version))
            self._log("success", t("update.found_log", version=info.version, tag=info.tag))
        else:
            self.update_status.configure(text=t("update.current", version=APP_VERSION), fg=C.green)
            if not silent:
                self._log("info", t("update.none_log"))
        self._update_buttons()

    def _handle_update_ready(self, path, version, error) -> None:
        self.update_busy = False
        self.check_btn.set_enabled(True)
        if error:
            self.install_btn.set_enabled(True)
            self.update_status.configure(text=t("update.failed_download"), fg=C.red)
            self._log("error", t("log.update_download_failed", error=error))
            messagebox.showerror(t("msg.update_title"), error, parent=self.root)
            return
        self._log("success", t("update.downloaded_log", version=version))
        self._install_now(path, version)

    def _tick(self) -> None:
        if self.running and self.next_run is not None:
            remaining = max(0, self.next_run - time.time())
            span = max(1, self.interval_sec)
            frac = 1.0 - min(1.0, remaining / span)
            self.gauge.set(
                frac,
                f"{int(remaining) // 60:02d}:{int(remaining) % 60:02d}",
                t("tick.next"),
                self.status_color,
            )
        elif self.running or self.busy:
            self.gauge.set((time.time() * 0.4) % 1.0, "•••", self.status_text,
                           self.status_color)
        else:
            self.gauge.set(0.0, "—", self.status_text, self.status_color)
        if self.run_started and not self.running:
            self.run_started = None
            self._update_stats()
        elif self.run_started:
            self._update_stats()
        self.root.after(120, self._tick)

    def _on_close(self) -> None:
        if self._installing:
            self.root.destroy()
            return
        if self.running or self.busy:
            if not messagebox.askyesno(
                t("msg.exit_title"),
                t("msg.exit_running"),
                parent=self.root,
            ):
                return
        self.stop_event.set()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Self test (python wan_ip_remover.pyw --selftest)
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

    # 1) CGI response parsing
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
    check("CGI: two records parsed", len(entries) == 2, f"len={len(entries)}")
    check(
        "CGI: stack is correct",
        entries and entries[0].get("__stack") == "1,1,1,0,0,0",
    )
    check(
        "CGI: name and status are correct",
        entries and entries[0].get("name") == "dsl_internet"
        and entries[0].get("connectionStatus") == "Connected",
    )
    check(
        "CGI: IP is correct",
        entries and entries[0].get("externalIPAddress") == "88.241.10.20",
    )
    check(
        "CGI: [error] line is not a record",
        all("__stack" in entry for entry in entries),
    )
    check(
        "Pick: exact name match",
        choose_entry(entries, "dsl_internet") is entries[0],
    )
    check("Pick: unknown name is None", choose_entry(entries, "missing") is None)
    check(
        "Pick: empty target takes the connected one",
        choose_entry(entries, "") is entries[0],
    )
    check(
        "Pick: found by stack",
        find_entry(entries, "dsl_internet", "1,1,1,0,0,0") is entries[0],
    )

    # 2) Address helpers
    check(
        "Address: strips http:// and trailing /",
        normalize_host("http://192.168.1.1/") == "192.168.1.1",
    )
    check("Address: empty input", normalize_host("   ") == "")
    check("IP: 0.0.0.0 counts as empty", clean_ip("0.0.0.0") == "")
    check("IP: valid IP is kept", clean_ip(" 1.2.3.4 ") == "1.2.3.4")

    # 3) Login page heuristic
    check(
        "Login page is recognised",
        looks_like_login_page('<html><input id="pc-login-password"></html>'),
    )
    check(
        "CGI response is not taken for a login page",
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
    check("RSA: hex length equals modulus", len(hex_value) == k * 2)
    check("RSA: lowercase hex", hex_value == hex_value.lower())
    decoded = pow(int(hex_value, 16), d, n).to_bytes(k, "big")
    check(
        "RSA: PKCS#1 type 2 layout",
        decoded[:2] == b"\x00\x02" and decoded.endswith(b"\x00" + message),
    )
    separator = decoded.rfind(b"\x00")
    check("RSA: at least 8 padding bytes", separator >= 10, f"separator={separator}")
    check(
        "RSA: padding bytes are non-zero",
        b"\x00" not in decoded[2:separator],
    )
    fake_n = (1 << 1023) | 1
    fake_hex = rsa_encrypt(b"x", fake_n, 65537)
    check("RSA: 1024-bit output is 256 hex", len(fake_hex) == 256, f"len={len(fake_hex)}")

    # 5) Password storage (DPAPI on Windows, plain-text fallback otherwise)
    settings = Settings()
    settings.set_password("secret-password-123")
    check("Password: stored", settings.has_password())
    check("Password: read back", settings.password() == "secret-password-123")
    if os.name == "nt":
        encoded = dpapi_protect("probe")
        check("DPAPI: encrypt", encoded is not None)
        if encoded:
            check("DPAPI: decrypt", dpapi_unprotect(encoded) == "probe")

    # 6) Update helpers
    check("Version: parses v2.1.3", version_tuple("v2.1.3") == (2, 1, 3))
    check("Version: empty text", version_tuple("n/a") == ())
    check("Version: newer detected", is_newer("v2.1.0", "2.0.0"))
    check("Version: same is not newer", not is_newer("v2.0.0", "2.0.0"))
    check("Version: older is not newer", not is_newer("v1.9.9", "2.0.0"))
    check("Version: multi-digit compare", is_newer("v2.0.10", "2.0.9"))

    release = {
        "tag_name": "v2.1.0",
        "body": "Release notes",
        "assets": [
            {"name": "baska.txt", "browser_download_url": "https://example.com/x"},
            {
                "name": UPDATE_ASSET,
                "browser_download_url": "https://example.com/app.pyw",
                "size": 12345,
            },
        ],
    }
    info = parse_release(release)
    check("Update: version read", info is not None and info.version == "2.1.0")
    check("Update: asset URL", info is not None and info.url.endswith("app.pyw"))
    check(
        "Update: no asset yields None",
        parse_release({"tag_name": "v2.1.0", "assets": []}) is None,
    )

    with tempfile.TemporaryDirectory() as folder:
        valid = Path(folder) / "valid.pyw"
        valid.write_text(
            f'APP_VERSION = "{APP_VERSION}"\n'
            "class RouterClient:\n    pass\n"
            "class App:\n    pass\n",
            encoding="utf-8",
        )
        try:
            Updater.validate(valid, APP_VERSION)
            valid_ok = True
        except UpdateError:
            valid_ok = False
        check("Update: valid file accepted", valid_ok)

        bad = Path(folder) / "bad.pyw"
        bad.write_text(
            'APP_VERSION = "9.9.9"\nclass RouterClient: pass\nclass App: pass\n',
            encoding="utf-8",
        )
        try:
            Updater.validate(bad, APP_VERSION)
            wrong_rejected = False
        except UpdateError:
            wrong_rejected = True
        check("Update: wrong version rejected", wrong_rejected)

        broken = Path(folder) / "broken.pyw"
        broken.write_text(
            f'APP_VERSION = "{APP_VERSION}"\nclass RouterClient: pass\nclass App: (\n',
            encoding="utf-8",
        )
        try:
            Updater.validate(broken, APP_VERSION)
            broken_rejected = False
        except UpdateError:
            broken_rejected = True
        check("Update: broken code rejected", broken_rejected)

    print()
    if failures:
        print(f"{len(failures)} tests failed: {', '.join(failures)}")
        return 1
    print("ALL TESTS PASSED")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    global FORCED_LANG
    if "--selftest" in sys.argv:
        return run_selftest()

    for arg in sys.argv:
        if arg.startswith("--lang="):
            value = arg.split("=", 1)[1].strip().lower()
            if value in ("tr", "en"):
                FORCED_LANG = value
    smoke = "--smoke" in sys.argv
    demo = "--demo" in sys.argv
    enable_dpi_awareness()
    root = tk.Tk()
    app = App(
        root,
        check_updates=not smoke and not demo and "--no-update-check" not in sys.argv,
        demo=demo,
    )
    root.protocol("WM_DELETE_WINDOW", app._on_close)
    if smoke:
        root.after(1200, root.destroy)
    root.mainloop()
    if smoke:
        print("GUI smoke test OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
