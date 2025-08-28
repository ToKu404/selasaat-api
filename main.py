from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# Inisialisasi aplikasi FastAPI
app = FastAPI(
    title="SELASAAT Landing Page",
    description="Website resmi untuk aplikasi photobox SELASAAT."
)

# 1. 'Mounting' folder 'static'
# Ini memberitahu FastAPI bahwa semua file di dalam folder 'static'
# dapat diakses langsung oleh browser.
app.mount("/static", StaticFiles(directory="static"), name="static")


# 2. Membuat endpoint untuk halaman utama ('/')
# Saat seseorang membuka website Anda (contoh: selasaat.koyeb.app),
# fungsi ini akan dijalankan.
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
# Baris ini tidak wajib untuk Koyeb, tapi sangat berguna untuk testing di komputer lokal.
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)