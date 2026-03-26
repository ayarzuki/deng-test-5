"""
Local HTTP proxy that forwards to iproyal with NL geo credentials.
Chrome connects to localhost:18080 (no auth) -> this forwards to iproyal (with auth).
"""

import socket
import threading
import base64
import select
import sys

UPSTREAM_HOST = "geo.iproyal.com"
UPSTREAM_PORT = 12321
UPSTREAM_USER = "nucleus_candidate"
UPSTREAM_PASS = "ZFe8Bv1YmfvLuIzu_country-nl"
LOCAL_PORT = 18080


def proxy_auth_header():
    creds = base64.b64encode(f"{UPSTREAM_USER}:{UPSTREAM_PASS}".encode()).decode()
    return f"Proxy-Authorization: Basic {creds}\r\n"


def handle_connect(client_sock, host, port):
    """Handle HTTPS CONNECT tunneling."""
    try:
        upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=15)
        # Send CONNECT to upstream with auth
        connect_req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n{proxy_auth_header()}\r\n"
        upstream.sendall(connect_req.encode())

        # Read upstream response
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = upstream.recv(4096)
            if not chunk:
                break
            response += chunk

        if b"200" in response.split(b"\r\n")[0]:
            client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            # Tunnel data bidirectionally
            tunnel(client_sock, upstream)
        else:
            client_sock.sendall(response)
    except Exception as e:
        try:
            client_sock.sendall(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{e}".encode())
        except Exception:
            pass
    finally:
        client_sock.close()


def handle_http(client_sock, method, url, headers_rest):
    """Handle plain HTTP requests (forward with auth)."""
    try:
        upstream = socket.create_connection((UPSTREAM_HOST, UPSTREAM_PORT), timeout=15)
        # Forward request with added auth header
        request = f"{method} {url} HTTP/1.1\r\n{proxy_auth_header()}{headers_rest}\r\n"
        upstream.sendall(request.encode())
        tunnel(client_sock, upstream)
    except Exception as e:
        try:
            client_sock.sendall(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{e}".encode())
        except Exception:
            pass
    finally:
        client_sock.close()


def tunnel(sock1, sock2):
    """Bidirectional data forwarding."""
    socks = [sock1, sock2]
    try:
        while True:
            readable, _, errored = select.select(socks, [], socks, 30)
            if errored:
                break
            if not readable:
                break
            for s in readable:
                data = s.recv(65536)
                if not data:
                    return
                other = sock2 if s is sock1 else sock1
                other.sendall(data)
    except Exception:
        pass
    finally:
        sock1.close()
        sock2.close()


def handle_client(client_sock):
    try:
        data = b""
        while b"\r\n" not in data:
            chunk = client_sock.recv(4096)
            if not chunk:
                client_sock.close()
                return
            data += chunk

        # Read remaining headers
        while b"\r\n\r\n" not in data:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            data += chunk

        first_line = data.split(b"\r\n")[0].decode()
        parts = first_line.split(" ")
        method = parts[0]
        url = parts[1] if len(parts) > 1 else ""

        # Get rest of headers (skip first line, remove any existing Proxy-Authorization)
        header_lines = data.decode().split("\r\n")[1:]
        filtered = [h for h in header_lines if not h.lower().startswith("proxy-authorization:")]
        headers_rest = "\r\n".join(filtered)

        if method == "CONNECT":
            # HTTPS tunnel
            host_port = url.split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 443
            handle_connect(client_sock, host, port)
        else:
            handle_http(client_sock, method, url, headers_rest)
    except Exception:
        client_sock.close()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", LOCAL_PORT))
    server.listen(50)
    print(f"Local proxy on 127.0.0.1:{LOCAL_PORT} -> {UPSTREAM_HOST}:{UPSTREAM_PORT} (NL geo)", flush=True)

    while True:
        client_sock, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client_sock,), daemon=True)
        t.start()


if __name__ == "__main__":
    main()
