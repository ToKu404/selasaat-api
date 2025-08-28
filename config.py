# config.py
import os
from dotenv import load_dotenv

load_dotenv() # Memuat variabel dari file .env

class Settings:
    TRIPAY_API_KEY: str = os.environ.get("TRIPAY_API_KEY")
    TRIPAY_PRIVATE_KEY: str = os.environ.get("TRIPAY_PRIVATE_KEY")
    TRIPAY_MERCHANT_CODE: str = os.environ.get("TRIPAY_MERCHANT_CODE")

    TRIPAY_MODE: str = os.environ.get("TRIPAY_MODE", "sandbox")
    TRIPAY_API_URL: str = (
        "https://tripay.co.id/api-sandbox/"
        if TRIPAY_MODE == "sandbox"
        else "https://tripay.co.id/api/"
    )

    # Validasi saat inisialisasi
    if not all([TRIPAY_API_KEY, TRIPAY_PRIVATE_KEY, TRIPAY_MERCHANT_CODE]):
        raise RuntimeError(
            "Kredensial Tripay (API_KEY, PRIVATE_KEY, MERCHANT_CODE) "
            "belum diatur dalam environment variables."
        )

settings = Settings()