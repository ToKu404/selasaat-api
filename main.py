# main.py

import uvicorn
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# Impor router dari kedua aplikasi
from api.tripay import router as tripay_router
from api.voucher import router as voucher_router
from api.photobox import photobox as photobox_router # Nama router-nya adalah 'photobox'

app = FastAPI(
    title="SELASAAT Project (Gabungan)",
    description="Website resmi dan API untuk aplikasi photobox SELASAAT."
)

# 1. Tambahkan Middleware CORS dari Aplikasi 2
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Sebaiknya ganti dengan domain frontend Anda di produksi
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Mount kedua direktori statis
# Dari Aplikasi 1 (untuk landing page)
app.mount("/static", StaticFiles(directory="static"), name="static")
# Dari Aplikasi 2 (untuk gambar frame yang di-upload)
UPLOAD_FOLDER = "uploads"
os.makedirs(os.path.join(UPLOAD_FOLDER, "frames"), exist_ok=True)
app.mount(f"/{UPLOAD_FOLDER}", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")


# 3. Sertakan kedua router
app.include_router(tripay_router, prefix="/api", tags=["Tripay Payments"])
app.include_router(photobox_router, prefix="/api", tags=["Photobox"]) # Menggunakan prefix /api yang sama
app.include_router(voucher_router, prefix="/api", tags=["vouchers"]) 

# Endpoint dari Aplikasi 1
@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

@app.get("/api/status")
def get_status():
    return {"status": "ok", "app_name": "SELASAAT"}

@app.get("/voucher", response_class=HTMLResponse)
async def serve_voucher_page():
    with open("static/voucher.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/voucher/success", response_class=HTMLResponse)
async def serve_voucher_success_page():
    with open("static/voucher-success.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# ==========================================================

# 3. Mount static files (tetap diperlukan untuk CSS, gambar, dll.)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Menjalankan server
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9121, reload=True)