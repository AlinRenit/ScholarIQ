"""Offline guard for the end-to-end run (never shipped or imported by the app).

Python imports ``sitecustomize`` at start-up when it is on ``PYTHONPATH``. This
one refuses every socket connection and name lookup that is not on the local
machine, and appends each attempt to ``$SCHOLARIQ_NET_GUARD_LOG`` so the test
run can fail if the backend tried to reach the network.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import traceback

_LOG = os.environ.get("SCHOLARIQ_NET_GUARD_LOG")
_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", ""}


def _is_local(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    name = str(host).strip("[]").lower()
    if name in _LOCAL_NAMES:
        return True
    try:
        addr = ipaddress.ip_address(name.split("%")[0])
    except ValueError:
        return False
    return addr.is_loopback or addr.is_unspecified


def _refuse(what: str, target: object) -> None:
    if _LOG:
        stack = "".join(traceback.format_stack(limit=6)[:-2])
        with open(_LOG, "a", encoding="utf-8") as fh:
            fh.write(f"python {what} {target!r}\n{stack}\n")
    raise OSError(f"Outbound network access is blocked in the offline run: {target!r}")


_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex
_getaddrinfo = socket.getaddrinfo


def _check(sock: socket.socket, address: object) -> None:
    if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple):
        if not _is_local(address[0]):
            _refuse("connect", address)


def connect(self: socket.socket, address: object) -> None:
    _check(self, address)
    return _connect(self, address)  # type: ignore[arg-type]


def connect_ex(self: socket.socket, address: object) -> int:
    _check(self, address)
    return _connect_ex(self, address)  # type: ignore[arg-type]


def getaddrinfo(host: object, *args: object, **kwargs: object) -> list:  # type: ignore[type-arg]
    if not _is_local(host):
        _refuse("getaddrinfo", host)
    return _getaddrinfo(host, *args, **kwargs)  # type: ignore[arg-type]


if _LOG:
    # Record that the guard is active in this process; the run checks for it.
    with open(_LOG.replace("outbound.log", "guards.log"), "a", encoding="utf-8") as fh:
        fh.write(f"python {os.getpid()}\n")

socket.socket.connect = connect  # type: ignore[method-assign]
socket.socket.connect_ex = connect_ex  # type: ignore[method-assign]
socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
