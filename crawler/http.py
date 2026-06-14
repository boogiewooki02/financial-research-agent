from __future__ import annotations

import ssl

import truststore


def create_ssl_context() -> ssl.SSLContext:
    """Use the operating system trust store without disabling TLS validation."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

