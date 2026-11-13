# Copyright (C) 2024-2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import socket
import stat
from concurrent.futures import ProcessPoolExecutor


def close_inherited_sockets():
    """Pool initializer: drop the TCP sockets a forked worker inherited from the server.

    Fork workers start with copies of uvicorn's listening socket and its client
    connections. While a worker holds a copy, a connection the server closes stays open
    (no FIN), so a client that keeps connections alive, like a sidecar proxy, sends its
    next request into it and waits; it is reset when the worker exits. Each such fd is
    pointed at /dev/null rather than closed, so the number stays taken and the server's
    socket objects the worker still has can not close an fd the worker opens later.
    Pipes (the pool's own queues) and Unix sockets are left alone.
    """
    try:
        fds = [int(fd) for fd in os.listdir("/proc/self/fd")]
    except OSError:  # no /proc
        return
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        for fd in fds:
            if fd == devnull:
                continue
            try:
                if not stat.S_ISSOCK(os.fstat(fd).st_mode):
                    continue
                s = socket.socket(fileno=fd)
                family = s.family
                s.detach()
                if family in (socket.AF_INET, socket.AF_INET6):
                    os.dup2(devnull, fd)
            except OSError:  # closed meanwhile (the listdir fd itself)
                continue
    finally:
        os.close(devnull)


def new_process_pool(max_workers):
    """A ProcessPoolExecutor whose workers do not hold the server's connections."""
    return ProcessPoolExecutor(max_workers=max_workers, initializer=close_inherited_sockets)
