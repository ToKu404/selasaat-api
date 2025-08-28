# main.py
# Hapus: from dotenv import load_dotenv, load_dotenv(), os, dan semua baris TRIPAY_*

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.tripay import router as tripay_router
from config import settings # <-- Impor settings dari config.py

# Inisialisasi aplikasi FastAPI
app = FastAPI(
    title="SELASAAT Landing Page",
    description="Website resmi untuk aplikasi photobox SELASAAT."
)

# (Kode lainnya tetap sama)
# ...

# 1. 'Mounting' folder 'static'
# Ini memberitahu FastAPI bahwa semua file di dalam folder 'static'
# dapat diakses langsung oleh browser.
app.mount("/static", StaticFiles(directory="static"), name="static")

# 2. Sertakan router Tripay
app.include_router(tripay_router, prefix="/api")

# 3. Membuat endpoint untuk halaman utama ('/')
@app.get("/")
async def read_root():
    """
    Fungsi ini akan mengirimkan file index.html sebagai respons.
    """
    return FileResponse('static/index.html')

# (Opsional) Endpoint untuk pengecekan status
@app.get("/api/status")
def get_status():
    """Endpoint sederhana untuk memastikan server berjalan."""
    return {"status": "ok", "app_name": "SELASAAT"}

# Perintah untuk menjalankan server saat file ini dieksekusi
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)