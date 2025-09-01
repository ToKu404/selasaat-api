# api/photobox.py

import os
import asyncio
import logging
import base64
from uuid import uuid4
from io import BytesIO
from typing import List
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from PIL import Image, ImageOps
from decimal import Decimal
from http import HTTPStatus


# --- Analisis Gambar ---
import cv2
import numpy as np

# --- SQLAlchemy & Database Imports ---
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.exc import SQLAlchemyError
from config.database import get_db
# PERBARUI IMPORT MODEL
from models.models import (
    PhotoSession, Frame, Package, FramePosition, Transaction, OrderItem, Voucher, Capture
)

# --- TAMBAHKAN: Import R2 client helper kita ---
from config.r2 import get_r2_client, R2_BUCKET_NAME, R2_PUBLIC_URL

# Inisialisasi Router
photobox = APIRouter()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==============================================================================
# MODELS (Pydantic) UNTUK REQUEST BODY
# (Tidak ada perubahan signifikan di sini, hanya nama model yang mungkin disesuaikan)
# ==============================================================================
class PhotoPlacement(BaseModel):
    url: str
    x: float
    y: float
    width: float
    height: float

class ComposeRequest(BaseModel):
    frame_url: str
    filter_name: str
    photos: List[PhotoPlacement]
    email_recipient: str | None = None

class SetFrameRequest(BaseModel):
    frame_id: str

class PackageCreateRequest(BaseModel):
    type: str
    price: Decimal
    services: str

# ==============================================================================
# FUNGSI HELPER
# ==============================================================================

def predict_photo_locations(image_bytes: BytesIO, min_area_threshold: int = 1000):
    """Menganalisis byte gambar PNG untuk menemukan area transparan."""
    try:
        img = Image.open(image_bytes)
        if img.format != 'PNG':
            raise ValueError("Format gambar harus PNG untuk mendukung transparansi.")
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        frame_width, frame_height = img.size
        frame_np = np.array(img)
        alpha_channel = frame_np[:, :, 3]
        _, binary_mask = cv2.threshold(alpha_channel, 0, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        positions = []
        for contour in contours:
            if cv2.contourArea(contour) > min_area_threshold:
                x, y, w, h = cv2.boundingRect(contour)
                positions.append({"x": int(x), "y": int(y), "width": int(w), "height": int(h)})

        if not positions:
            raise ValueError("Tidak ada area foto transparan yang valid terdeteksi.")
        
        positions.sort(key=lambda p: p['y'])
        return {"width": frame_width, "height": frame_height, "positions": positions}
    except Exception as e:
        raise ValueError(f"Gagal memproses gambar: {str(e)}")

def apply_filter(image: Image.Image, filter_name: str) -> Image.Image:
    """Mengaplikasikan filter ke gambar Pillow."""
    if filter_name == "grayscale":
        return ImageOps.grayscale(image).convert("RGBA")
    if filter_name == "sepia":
        sepia_image = image.copy().convert("L")
        sepia_image = ImageOps.colorize(sepia_image, black="#704214", white="#E6D8B4")
        return sepia_image.convert(image.mode)
    return image

def send_email_with_attachment(recipient_email: str, file_path: str):
    """Placeholder untuk fungsi pengiriman email."""
    logging.info(f"Fungsi kirim email dipanggil untuk {recipient_email} dengan file {file_path}")
    pass

# ==============================================================================
# ENDPOINT /frames
# ==============================================================================

@photobox.get("/frames")
async def get_frames(response: Response, db: AsyncSession = Depends(get_db)):
    try:
        query = select(Frame).options(selectinload(Frame.positions)).distinct()
        result = await db.execute(query)
        frames = result.scalars().unique().all()
        if not frames:
            response.status_code = 404
            return {"status": "NOT_FOUND", "message": "No frames found"}

        data = [
            {"id": frame.id, "name": frame.name, "imageLink": frame.image_link, "width": frame.width, "height": frame.height,
             "positions": [{"id": pos.id, "x": pos.x, "y": pos.y, "width": pos.width, "height": pos.height} for pos in (frame.positions or [])],
             "createdAt": frame.created_at, "updatedAt": frame.updated_at}
            for frame in frames
        ]
        return {"status": "SUCCESS", "data": data}
    except SQLAlchemyError as e:
        response.status_code = 500
        return {"status": "ERROR", "message": str(e)}



@photobox.post("/frames")
async def add_frame(db: AsyncSession = Depends(get_db), name: str = Form(...), frame_image: UploadFile = File(...)):
    contents = await frame_image.read()
    if not contents:
        raise HTTPException(status_code=400, detail="File yang diunggah kosong.")
    try:
        prediction_data = predict_photo_locations(BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal memproses gambar frame: {e}")

    r2_client = get_r2_client()
    if not r2_client:
        raise HTTPException(status_code=500, detail="Layanan penyimpanan R2 tidak tersedia.")

    file_extension = os.path.splitext(frame_image.filename)[1]
    object_key = f"frames/{uuid4()}{file_extension}"
    public_url = f"{R2_PUBLIC_URL}/{object_key}"

    try:
        
        r2_client.put_object(Bucket=R2_BUCKET_NAME, Key=object_key, Body=contents, ContentType=frame_image.content_type)
        new_frame = Frame(
            id=str(uuid4()), name=name, image_link=public_url, width=prediction_data['width'], height=prediction_data['height']
        )
        new_frame.positions = [
            FramePosition(id=str(uuid4()), x=pos['x'], y=pos['y'], width=pos['width'], height=pos['height'])
            for pos in prediction_data['positions']
        ]
        db.add(new_frame)
        await db.commit()
        await db.refresh(new_frame)
        
        return {"status": "SUCCESS", "data": {
                "id": new_frame.id, "name": new_frame.name, "imageLink": new_frame.image_link, "width": new_frame.width,
                "height": new_frame.height, "positions": prediction_data['positions'],
                "createdAt": new_frame.created_at, "updatedAt": new_frame.updated_at,
            }}
    except Exception as e:
        try:
            r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
        except Exception as delete_e:
            logging.error(f"Gagal melakukan rollback upload R2 untuk key {object_key}: {delete_e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan: {e}")

@photobox.delete("/frames/{frame_id}")
async def delete_frame(frame_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Frame).filter_by(id=frame_id))
    frame = result.scalars().first()
    if not frame:
        raise HTTPException(status_code=404, detail="Frame tidak ditemukan.")

    image_url = frame.image_link
    await db.delete(frame)
    await db.commit()
    
    if image_url:
        r2_client = get_r2_client()
        if r2_client:
            object_key = urlparse(image_url).path.lstrip('/')
            try:
                r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=object_key)
            except Exception as e:
                logging.error(f"Gagal menghapus objek {object_key} dari R2: {e}")
    return {"status": "SUCCESS", "message": f"Frame dengan ID {frame_id} berhasil dihapus."}

# ==============================================================================
# ENDPOINT /captures & /compose
# ==============================================================================

# api/photobox.py

# api/photobox.py

@photobox.post("/captures", status_code=HTTPStatus.CREATED)
async def upload_capture(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    frame_position_id: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    # 1. Validasi Session dan FramePosition
    session_result = await db.execute(select(PhotoSession).filter_by(id=session_id))
    if not session_result.scalars().first():
        raise HTTPException(status_code=404, detail="PhotoSession not found")

    position_result = await db.execute(select(FramePosition).filter_by(id=frame_position_id))
    position_data = position_result.scalars().first()
    if not position_data:
        raise HTTPException(status_code=404, detail="FramePosition not found")

    # 2. Baca file dan siapkan untuk diunggah
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="File cannot be empty.")

    r2_client = get_r2_client()
    if not r2_client:
        raise HTTPException(status_code=500, detail="R2 storage service is unavailable.")

    img = Image.open(BytesIO(contents)).convert("RGBA")
    
    original_key = f"captures/{session_id}/{uuid4()}_original.png"
    normal_key = f"captures/{session_id}/{uuid4()}_normal.png"
    
    # 3. Proses dan Unggah ke R2
    try:
        original_buffer = BytesIO()
        img.save(original_buffer, format="PNG")
        original_buffer.seek(0)
        r2_client.put_object(Bucket=R2_BUCKET_NAME, Key=original_key, Body=original_buffer, ContentType='image/png')

        normal_buffer = BytesIO()
        thumbnail_size = (position_data.width, position_data.height)
        
        normal_img = img.copy()
        normal_img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
        normal_img.save(normal_buffer, format="PNG", optimize=True)
        normal_buffer.seek(0)
        r2_client.put_object(Bucket=R2_BUCKET_NAME, Key=normal_key, Body=normal_buffer, ContentType='image/png')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to R2: {e}")

    # 4. Simpan data capture ke database
    new_capture = Capture(
        id=str(uuid4()),
        session_id=session_id,
        raw_capture_url=f"{R2_PUBLIC_URL}/{original_key}",
        normal_capture_url=f"{R2_PUBLIC_URL}/{normal_key}",
        frame_position_id=frame_position_id
    )
    
    try:
        db.add(new_capture)
        await db.commit()
    except Exception as e:
        await db.rollback()
        try:
            r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=original_key)
            r2_client.delete_object(Bucket=R2_BUCKET_NAME, Key=normal_key)
        except Exception as delete_e:
            logger.error(f"Failed to delete R2 objects during rollback: {delete_e}")
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan data capture: {e}")

    return {
        "original": new_capture.raw_capture_url,
        "normal": new_capture.normal_capture_url,
        "x": position_data.x,
        "y": position_data.y,
        "width": position_data.width,
        "height": position_data.height,
    }

@photobox.post("/compose")
async def compose_high_res_photo(request: ComposeRequest):
    PRINT_DPI, FINAL_WIDTH_PX = 300, 4 * 300
    r2_client = get_r2_client()
    if not r2_client:
        raise HTTPException(status_code=500, detail="Layanan penyimpanan R2 tidak tersedia.")
    try:
        frame_key = urlparse(request.frame_url).path.lstrip('/')
        frame_obj = r2_client.get_object(Bucket=R2_BUCKET_NAME, Key=frame_key)
        frame_image = Image.open(frame_obj['Body']).convert("RGBA")
        
        aspect_ratio = frame_image.width / frame_image.height
        final_height = int(FINAL_WIDTH_PX / aspect_ratio)
        canvas = Image.new("RGBA", (FINAL_WIDTH_PX, final_height), (255, 255, 255, 255))
        
        for photo_data in request.photos:
            photo_key = urlparse(photo_data.url).path.lstrip('/')
            photo_obj = r2_client.get_object(Bucket=R2_BUCKET_NAME, Key=photo_key)
            photo_img = Image.open(photo_obj['Body']).convert("RGBA")
            filtered_photo = apply_filter(photo_img, request.filter_name)
            
            scale_w, scale_h = FINAL_WIDTH_PX / frame_image.width, final_height / frame_image.height
            paste_x, paste_y = int(photo_data.x * scale_w), int(photo_data.y * scale_h)
            paste_w, paste_h = int(photo_data.width * scale_w), int(photo_data.height * scale_h)
            
            resized_photo = filtered_photo.resize((paste_w, paste_h), Image.Resampling.LANCZOS)
            canvas.paste(resized_photo, (paste_x, paste_y), resized_photo)

        resized_frame = frame_image.resize((FINAL_WIDTH_PX, final_height), Image.Resampling.LANCZOS)
        canvas.paste(resized_frame, (0, 0), resized_frame)
        
        final_key, final_buffer = f"final/{uuid4()}_final.png", BytesIO()
        final_image_rgb = canvas.convert("RGB")
        final_image_rgb.save(final_buffer, format="PNG", dpi=(PRINT_DPI, PRINT_DPI))
        final_buffer.seek(0)
        r2_client.put_object(Bucket=R2_BUCKET_NAME, Key=final_key, Body=final_buffer, ContentType='image/png')
        
        if request.email_recipient:
            # send_email_with_attachment(request.email_recipient, final_path)
            pass
        return {"status": "SUCCESS", "final_image_url": f"{R2_PUBLIC_URL}/{final_key}", "email_sent_to": request.email_recipient}
    except Exception as e:
        logging.error(f"Gagal membuat gambar final: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# ENDPOINT /sessions
# ==============================================================================

@photobox.put("/session/{session_id}/frame")
async def set_frame(session_id: str, request: SetFrameRequest, db: AsyncSession = Depends(get_db)):
    try:
        # Diubah: filter by 'id' bukan 'session_id'
        result = await db.execute(select(PhotoSession).filter_by(id=session_id))
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session.frame_id = request.frame_id
        await db.commit()
        return {"data": {"message": "Frame ID updated successfully"}}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail={"data": {"message": str(e)}})


@photobox.post("/sessions")
async def create_session(name: str = Form(...),session_id: str = Form(...), transaction_id: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not name or not transaction_id or not session_id: 
        raise HTTPException(status_code=400, detail="Name and Transaction ID are required")
    
    # Periksa apakah transaksi ada
    res = await db.execute(select(Transaction).filter_by(id=transaction_id))
    if not res.scalars().first():
        raise HTTPException(status_code=404, detail="Transaction not found")

    new_session = PhotoSession(
        id=session_id, 
        name=name,
        transaction_id=transaction_id
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return {"status": "SUCCESS", "data": new_session.id}

@photobox.get("/sessions")
async def get_photo_sessions(response: Response, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(PhotoSession))
        sessions = result.unique().scalars().all()
        if not sessions:
            response.status_code = HTTPStatus.NOT_FOUND
            return {"status": "NOT_FOUND", "message": "No photo sessions found"}
        
        # PERBAIKAN DI SINI:
        data = [{"sessionId": s.id, "name": s.name, "recipientEmail": s.recipient_email} for s in sessions]
        
        return {"status": "SUCCESS", "data": data}
    except Exception as e:
        logger.error(f"Error getting sessions: {str(e)}", exc_info=True)
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return {"status": "ERROR", "message": "Internal Server Error"}
# ==============================================================================
# ENDPOINT /packages
# ==============================================================================

@photobox.post("/packages")
async def create_package(request: PackageCreateRequest, db: AsyncSession = Depends(get_db)):
    try:
        new_package = Package(id=str(uuid4()), type=request.type, price=request.price, services=request.services)
        db.add(new_package)
        await db.commit()
        await db.refresh(new_package)
        return {"status": "SUCCESS", "data": {
            "id": new_package.id, "type": new_package.type, "price": new_package.price, 
            "services": new_package.services.split(',') if new_package.services else []
        }}
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail={"status": "ERROR", "message": str(e)})

@photobox.get("/packages")
async def get_all_packages(response: Response, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(Package))
        packages = result.scalars().all()
        if not packages:
            response.status_code = 404
            return {"status": "NOT_FOUND", "message": "No packages found"}
        data = [{"id": pkg.id, "type": pkg.type, "price": pkg.price, 
                 "services": pkg.services.split(',') if pkg.services else []} for pkg in packages]
        return {"status": "SUCCESS", "data": data}
    except SQLAlchemyError as e:
        response.status_code = 500
        return {"status": "ERROR", "message": str(e)}

# ==============================================================================
# DATABASE HELPER METHODS UNTUK TRANSAKSI (INTERNAL)
# ==============================================================================

# api/photobox.py

# Di dalam file: api/photobox.py

async def _save_transaction_to_db(db: AsyncSession, tripay_data: dict, order_items: list, transaction_type: str) -> str:
    """Menyimpan transaksi baru dan item-item terkaitnya ke database, lalu return transaction_id."""
    try:
        new_transaction = Transaction(
            id=str(uuid4()),
            reference=tripay_data.get('reference'),
            merchant_ref=tripay_data.get('merchant_ref'),
            transaction_type=transaction_type,
            payment_method=tripay_data.get('payment_method'),
            payment_name=tripay_data.get('payment_name'),
            customer_name=tripay_data.get('customer_name'),
            customer_email=tripay_data.get('customer_email'),
            customer_phone=tripay_data.get('customer_phone'),
            amount=Decimal(str(tripay_data.get('amount'))),
            
            # === PERBAIKAN DI SINI ===
            status='PENDING', # Diubah dari 'UNPAID' menjadi 'PENDING'
            # =========================

            expired_time=tripay_data.get('expired_time'),
            checkout_url=tripay_data.get('checkout_url'),
            qr_string=tripay_data.get('qr_string'),
            qr_url=tripay_data.get('qr_url')
        )
        db.add(new_transaction)
        await db.flush()

        for item in order_items:
            package_id = item.get('id')
            
            if not package_id:
                raise ValueError("ID Paket tidak ditemukan di dalam item pesanan.")

            new_order_item = OrderItem(
                id=str(uuid4()),
                transaction_id=new_transaction.id,
                package_id=package_id,
                item_name=item.get('name'),
                item_price=Decimal(str(item.get('price'))),
                quantity=item.get('quantity')
            )
            db.add(new_order_item)

        if transaction_type == 'VOUCHER':
            main_item = order_items[0]
            new_voucher = Voucher(
                id=str(uuid4()),
                package_id=main_item.get('id'),
                transaction_id=new_transaction.id,
                recipient_email=tripay_data.get('customer_email'),
                status='PENDING_PAYMENT'
            )
            db.add(new_voucher)

        await db.commit()
        logger.info(f"Berhasil menyimpan transaksi {new_transaction.merchant_ref} ke database.")
        return new_transaction.id
    except Exception as e:
        await db.rollback()
        logger.error(f"Gagal menyimpan transaksi {tripay_data.get('merchant_ref')} ke DB: {e}", exc_info=True)
        raise e
    

# Di bagian paling atas file api/photobox.py, tambahkan import ini

# Di bagian Pydantic Models, tambahkan model request ini
# ... (import-import lainnya di bagian atas) ...
# --- SQLAlchemy & Database Imports ---
# ... (import-import lainnya) ...

# 1. HAPUS BARIS INI DARI BAGIAN ATAS FILE
# from api.payment import midtrans_service  <-- HAPUS INI

# ... (kode lainnya) ...

# Di bagian Pydantic Models, tambahkan model request ini
class CreatePhotosessionTransactionRequest(BaseModel):
    package_id: str
    customer_name: str
    customer_email: str

# Di bagian paling bawah file, ubah endpoint ini
@photobox.post("/transactions/request-photosession")
async def request_photosession_transaction(request: CreatePhotosessionTransactionRequest, db: AsyncSession = Depends(get_db)):
    """Membuat transaksi Midtrans QRIS khusus untuk Photo Session."""

    # 2. TAMBAHKAN BARIS IMPOR DI DALAM FUNGSI INI
    from api.payment import midtrans_service

    package_result = await db.execute(select(Package).filter_by(id=request.package_id))
    package = package_result.scalars().first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    order_id = f"SESI-{os.urandom(4).hex().upper()}"
    payload = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": int(package.price)
        }
    }

    try:
        midtrans_response = await midtrans_service.create_qris_transaction(payload)
        
        qr_string = midtrans_response.get('qr_string')
        qr_url = next((a['url'] for a in midtrans_response.get('actions', []) if a['name'] == 'generate-qr-code'), None)

        db_transaction_data = {
            "merchant_ref": order_id,
            "reference": midtrans_response.get("transaction_id"),
            "amount": int(package.price),
            "status": "PENDING",
            "customer_email": request.customer_email,
            "customer_name": request.customer_name,
            "payment_method": "qris", "payment_name": "QRIS",
            "qr_string": qr_string, "qr_url": qr_url
        }
        
        order_items = [{
            "id": package.id, "price": int(package.price), "quantity": 1,
            "name": f"Photo Session - {package.type}"
        }]
        
        transaction_id = await _save_transaction_to_db(
            db=db,
            tripay_data=db_transaction_data,
            order_items=order_items,
            transaction_type='PHOTOSESSION'
        )

        return {
            "data": {
                "order_id": order_id,
            "qr_string": qr_string,
            "qr_url": qr_url,
            "transaction_id": transaction_id,
            }
        }
    except Exception as e:
        logger.error(f"Error requesting photosession transaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
async def _update_transaction_status_in_db(db: AsyncSession, reference: str, new_status: str, amount_received: Decimal = None):
    """Mengupdate status transaksi dan menjalankan logika pasca-pembayaran (webhook)."""
    try:
        result = await db.execute(
            select(Transaction).options(
                selectinload(Transaction.vouchers), # Load relasi voucher
                selectinload(Transaction.order_items) # Load relasi order items
            ).filter_by(reference=reference)
        )
        transaction = result.scalars().first()
        if not transaction:
            logger.warning(f"Update gagal: Transaksi dengan referensi {reference} tidak ditemukan.")
            return

        transaction.status = new_status
        if new_status == 'PAID' and amount_received is not None:
            transaction.amount_received = amount_received

        # --- LOGIKA PASCA-PEMBAYARAN ---
        if new_status == 'PAID':
            if transaction.transaction_type == 'PHOTOSESSION':
                # Buat PhotoSession baru secara otomatis
                new_session = PhotoSession(
                    id=str(uuid4()),
                    transaction_id=transaction.id,
                    name=transaction.customer_name,
                    recipient_email=transaction.customer_email
                )
                db.add(new_session)
                logger.info(f"PhotoSession baru dibuat untuk transaksi {reference}.")

            elif transaction.transaction_type == 'VOUCHER':
                # Aktifkan voucher yang sudah ada
                if transaction.vouchers:
                    voucher_to_activate = transaction.vouchers[0]
                    voucher_to_activate.status = 'ACTIVE'
                    # Hasilkan kode unik di sini
                    voucher_to_activate.code = f"VCR-{os.urandom(6).hex().upper()}"
                    logger.info(f"Voucher {voucher_to_activate.code} diaktifkan untuk transaksi {reference}.")
        
        await db.commit()
        logger.info(f"Berhasil mengupdate transaksi {reference} menjadi {new_status}.")
    except Exception as e:
        await db.rollback()
        logger.error(f"Gagal mengupdate transaksi {reference} di DB: {e}", exc_info=True)


async def _get_transaction_by_order_id(db: AsyncSession, order_id: str) -> Transaction | None:
    """
    Mengambil data transaksi dari database berdasarkan order_id dari Midtrans,
    yang disimpan di kolom 'merchant_ref'.
    """
    try:
        # Membuat query untuk memilih transaksi
        query = select(Transaction).where(Transaction.merchant_ref == order_id)
        
        # Menjalankan query secara asynchronous
        result = await db.execute(query)
        
        # Mengambil satu hasil atau None jika tidak ditemukan
        transaction = result.scalars().first()
        
        return transaction
    except Exception as e:
        # Jika terjadi error pada database, log error tersebut (opsional)
        # dan kembalikan None agar tidak menghentikan aplikasi.
        print(f"Database error while fetching transaction by order_id: {e}")
        return None