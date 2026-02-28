#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Script para iniciar o servidor Flask"""
import os
import sys
import ssl
import ipaddress

# Muda para o diretório do projeto
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --- HTTPS support for mobile devices ---
# Mobile browsers require HTTPS for getUserMedia (microphone access).
# We generate a self-signed certificate if one doesn't exist.
CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.ssl')
CERT_FILE = os.path.join(CERT_DIR, 'cert.pem')
KEY_FILE = os.path.join(CERT_DIR, 'key.pem')

def ensure_ssl_cert():
    """Generate a self-signed SSL certificate for local HTTPS."""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return True
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime

        os.makedirs(CERT_DIR, exist_ok=True)

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"IA de Conversacao Dev"),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(u"localhost"),
                    x509.IPAddress(ipaddress.IPv4Address(u"127.0.0.1")),
                    x509.IPAddress(ipaddress.IPv4Address(u"0.0.0.0")),
                ]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        with open(KEY_FILE, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        with open(CERT_FILE, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        print("  [SSL] Certificado autoassinado gerado com sucesso.")
        return True
    except ImportError:
        print("  [SSL] Pacote 'cryptography' nao encontrado.")
        print("         Instale com: pip install cryptography")
        print("         Sem HTTPS, o microfone NAO funcionara no celular.")
        return False
    except Exception as e:
        print(f"  [SSL] Erro ao gerar certificado: {e}")
        return False

ssl_available = ensure_ssl_cert()

protocol = "https" if ssl_available else "http"
print("\n" + "="*60)
print("  INICIANDO SERVIDOR FLASK")
print("="*60)
print(f"\n  Diretório: {os.getcwd()}")
print(f"  Porta: 8912")
print(f"  URL: {protocol}://localhost:8912")
if ssl_available:
    print(f"  HTTPS: ATIVADO (certificado autoassinado)")
    print(f"  Mobile: Acesse via https://<seu-ip>:8912")
    print(f"  NOTA: No celular, aceite o aviso de certificado.")
else:
    print(f"  HTTPS: DESATIVADO (microfone pode nao funcionar no celular)")
print("\n" + "="*60 + "\n")

try:
    # Importa e executa o servidor
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from api.index import app

    ssl_context = None
    if ssl_available:
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)

    print("  Servidor iniciando...\n")
    app.run(debug=True, port=8912, host='0.0.0.0', use_reloader=False, ssl_context=ssl_context)
except KeyboardInterrupt:
    print("\n\n  Servidor encerrado pelo usuário.")
    sys.exit(0)
except Exception as e:
    print(f"\n\n  [ERRO] Falha ao iniciar servidor: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
