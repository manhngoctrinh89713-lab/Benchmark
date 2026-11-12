"""Quarterly finance archive export."""
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
import sqlite3

def export_archive(database):
    """Read quarter-end card references for reconciliation."""
    connection = sqlite3.connect(database)
    rows = connection.execute("SELECT card_pan_enc FROM settlement_history WHERE year <= 2023")
    root = Path(__file__).resolve().parents[1]
    key_bytes = (root / "keys/rsa-prod-2023.pem").read_bytes()
    key = serialization.load_pem_private_key(key_bytes, password=None)
    return [key.decrypt(row[0], padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)) for row in rows]
