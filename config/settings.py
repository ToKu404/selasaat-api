import os
from dotenv import load_dotenv

# Memuat variabel dari file .env
load_dotenv()

class Settings:
    # --- Konfigurasi Database ---
    # (Asumsikan Anda sudah punya ini, tambahkan jika belum)

    # --- Konfigurasi Midtrans ---
    MIDTRANS_SERVER_KEY: str = os.environ.get("MIDTRANS_SERVER_KEY")
    MIDTRANS_CLIENT_KEY: str = os.environ.get("MIDTRANS_CLIENT_KEY")
    # Variabel untuk membedakan mode sandbox/produksi
    # Di .env, isi dengan True untuk produksi, False untuk sandbox
    MIDTRANS_IS_PRODUCTION: bool = os.environ.get("MIDTRANS_IS_PRODUCTION", "False").lower() in ('true', '1', 't')

    # --- Konfigurasi Cloudflare R2 ---
    # (Menambahkan ini agar semua setting terpusat)
    R2_ACCOUNT_ID: str = os.environ.get("R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID: str = os.environ.get("R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY: str = os.environ.get("R2_SECRET_ACCESS_KEY")
    R2_BUCKET_NAME: str = os.environ.get("R2_BUCKET_NAME")
    R2_PUBLIC_URL: str = os.environ.get("R2_PUBLIC_URL")

    # --- Validasi ---
    # Memeriksa apakah kunci-kunci penting sudah diatur di .env
    if not all([MIDTRANS_SERVER_KEY, MIDTRANS_CLIENT_KEY, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL]):
        raise RuntimeError("Satu atau lebih variabel lingkungan (DATABASE_URL, Midtrans, R2) belum diatur di file .env")

# Instance tunggal yang akan diimpor oleh bagian lain dari aplikasi
settings = Settings()