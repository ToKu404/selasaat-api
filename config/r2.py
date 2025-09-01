# config/r2.py

import os
import boto3
from dotenv import load_dotenv

# Muat environment variables dari file .env
load_dotenv()

# Ambil konfigurasi dari environment
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL", "").rstrip('/') # Pastikan tidak ada slash di akhir

# Cek apakah semua variabel ada
if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL]):
    raise ValueError("Pastikan semua variabel R2 ada di file .env")

# Endpoint URL untuk R2
R2_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Fungsi untuk membuat dan mengembalikan client R2
def get_r2_client():
    """Membuat dan mengembalikan S3 client yang dikonfigurasi untuk Cloudflare R2."""
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name='auto', # 'auto' biasanya bekerja dengan baik untuk R2
        )
        return s3_client
    except Exception as e:
        print(f"Gagal membuat R2 client: {e}")
        return None