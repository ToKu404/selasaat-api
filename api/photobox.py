import base64
from decimal import Decimal
from http import HTTPStatus
from io import BytesIO
import logging
from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import os

# --- Tambahan import untuk logika prediksi ---
import cv2
import numpy as np
from PIL import Image
# --------------------------------------------

from config.database import get_db, Base # Impor dari lokasi baru
from models.models import PhotoSession, Payment, Frame, Package, FramePosition

photobox = APIRouter()


# ==============================================================================
# FUNGSI HELPER UNTUK PREDIKSI POSISI FOTO
# ==============================================================================
def predict_photo_locations(image_bytes: BytesIO, min_area_threshold: int = 1000):
    """
    Menganalisis byte gambar untuk menemukan area transparan (slot foto).
    Mengembalikan dictionary berisi dimensi dan daftar posisi.
    """
    try:
        # Buka gambar dari byte stream menggunakan Pillow
        img = Image.open(image_bytes)

        if img.format != 'PNG':
            raise ValueError(
                "Format gambar harus PNG untuk mendukung transparansi.")

        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        frame_width, frame_height = img.size
        # Konversi ke format OpenCV (array NumPy)
        frame_np = np.array(img)

        # Pisahkan channel alpha (indeks ke-3)
        alpha_channel = frame_np[:, :, 3]

        # Buat mask biner: 255 untuk area transparan (alpha=0), 0 untuk lainnya
        _, binary_mask = cv2.threshold(
            alpha_channel, 0, 255, cv2.THRESH_BINARY_INV)

        # Temukan kontur pada mask
        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        positions = []
        for contour in contours:
            if cv2.contourArea(contour) > min_area_threshold:
                x, y, w, h = cv2.boundingRect(contour)
                positions.append({"x": int(x), "y": int(
                    y), "width": int(w), "height": int(h)})

        if not positions:
            raise ValueError(
                "Tidak ada area foto transparan yang valid terdeteksi.")

        # Urutkan posisi dari atas ke bawah
        positions.sort(key=lambda p: p['y'])

        return {
            "width": frame_width,
            "height": frame_height,
            "positions": positions
        }
    except Exception as e:
        # Tangkap semua kemungkinan error dari pemrosesan gambar
        raise ValueError(f"Gagal memproses gambar: {str(e)}")


# ==============================================================================
# ENDPOINT FRAMES (GET, POST, DELETE)
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
            {
                "id": frame.id,
                "name": frame.name,
                "imageLink": frame.image_link,
                "width": frame.width,
                "height": frame.height,
                "positions": [
                    {
                        "x": pos.x, "y": pos.y, "width": pos.width, "height": pos.height,
                    } for pos in (frame.positions or [])
                ],
                "createdAt": frame.created_at,
                "updatedAt": frame.updated_at,
            }
            for frame in frames
        ]

        return {"status": "SUCCESS", "data": data}

    except SQLAlchemyError as e:
        response.status_code = 500
        return {"status": "ERROR", "message": str(e)}


# ... (semua import dan fungsi helper sama) ...

# ... (import dan fungsi lain tetap sama) ...
@photobox.post("/frames", status_code=HTTPStatus.CREATED)
async def add_frame(
    db: AsyncSession = Depends(get_db),
    name: str = Form(...),
    frame_image: UploadFile = File(...)
):
    UPLOAD_DIR = "uploads/frames"
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)

    file_extension = os.path.splitext(frame_image.filename)[1]
    unique_filename = f"{uuid4()}{file_extension}"
    file_location = os.path.join(UPLOAD_DIR, unique_filename)

    contents = None
    prediction_data = None

    try:
        contents = await frame_image.read()
        logging.info(
            f"Menerima file dengan nama: {frame_image.filename}, ukuran: {len(contents)} bytes")

        if not contents:
            logging.error("Isi file kosong, menolak permintaan.")
            raise HTTPException(
                status_code=400, detail="Uploaded file is empty.")

        image_bytes = BytesIO(contents)
        prediction_data = predict_photo_locations(image_bytes)

    except Exception as e:
        logging.error(
            f"Gagal memproses file atau menjalankan prediksi: {e}", exc_info=True)
        raise HTTPException(
            status_code=400, detail=f"Failed to process image: {e}")

    try:
        # Save the file to the local disk
        with open(file_location, "wb") as f:
            f.write(contents)

        # Create the database record
        new_frame = Frame(
            id=str(uuid4()),
            name=name,
            image_link=f"/{UPLOAD_DIR}/{unique_filename}",
            width=prediction_data['width'],
            height=prediction_data['height']
        )

        # Add frame positions
        new_frame.positions = [
            FramePosition(
                id=str(uuid4()),
                x=pos['x'], y=pos['y'],
                width=pos['width'], height=pos['height']
            ) for pos in prediction_data['positions']
        ]

        db.add(new_frame)
        await db.commit()
        await db.refresh(new_frame)

        return {
            "status": "SUCCESS",
            "data": {
                "id": new_frame.id,
                "name": new_frame.name,
                "imageLink": new_frame.image_link,
                "width": new_frame.width,
                "height": new_frame.height,
                "positions": prediction_data['positions'],
                "createdAt": new_frame.created_at,
                "updatedAt": new_frame.updated_at,
            }
        }
    except SQLAlchemyError as e:
        await db.rollback()
        if os.path.exists(file_location):
            os.remove(file_location)
        logging.error(f"Database error details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    except Exception as e:
        if os.path.exists(file_location):
            os.remove(file_location)
        logging.error(
            f"An unexpected error occurred during database/file saving: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {e}")
# ---ENDPOINT BARU: Menghapus Frame---


@photobox.delete("/frames/{frame_id}")
async def delete_frame(
    frame_id: str,
    db: AsyncSession = Depends(get_db)
):
    try:
        # Cari frame di database
        result = await db.execute(select(Frame).filter_by(id=frame_id))
        frame = result.scalars().first()

        if not frame:
            raise HTTPException(status_code=404, detail="Frame not found")

        # Simpan path gambar sebelum menghapus record dari DB
        image_path = frame.image_link.lstrip('/') if frame.image_link else None

        # Hapus record dari database (posisi terkait akan terhapus jika cascade di-setting)
        await db.delete(frame)
        await db.commit()

        # Hapus file gambar dari server
        if image_path and os.path.exists(image_path):
            os.remove(image_path)

        return {"status": "SUCCESS", "message": f"Frame with ID {frame_id} deleted."}
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Database error: {str(e)}")


# ==============================================================================
# ENDPOINT SESSIONS & PACKAGES (TETAP SAMA)
# ==============================================================================

# ... (sisa kode Anda dari sini tetap sama, tidak perlu diubah) ...
# (Saya sertakan lagi di bawah untuk kelengkapan)

class SetFrameRequest(BaseModel):
    frame_id: str


@photobox.put("/session/{session_id}/frame")
async def set_frame(session_id: str, request: SetFrameRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(select(PhotoSession).filter_by(session_id=session_id))
        session = result.scalars().first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session.frame_id = request.frame_id
        await db.commit()
        return {"data": {"message": "Frame ID updated successfully"}}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail={
                            "data": {"message": str(e)}})
    finally:
        await db.close()


@photobox.post("/sessions")
async def create_session(name: str, db: AsyncSession = Depends(get_db)):
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    session_id = str(uuid4())
    new_session = PhotoSession(session_id=session_id, name=name)
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)
    return {"status": "SUCCESS", "data": new_session.session_id}

logger = logging.getLogger(__name__)


@photobox.get("/sessions")
async def get_photo_sessions(response: Response, db: AsyncSession = Depends(get_db)):
    try:
        query = select(PhotoSession)
        result = await db.execute(query)
        sessions = result.unique().scalars().fetchall()
        if not sessions:
            response.status_code = HTTPStatus.NOT_FOUND
            return {"status": "NOT_FOUND", "message": "No photo sessions found"}
        data = []
        for session in sessions:
            encoded_image = None
            if session.result_image and session.result_image.image:
                encoded_image = base64.b64encode(
                    session.result_image.image).decode()
            session_data = {"sessionId": session.session_id, "name": session.name,
                            "email": session.email, "result_image": encoded_image}
            data.append(session_data)
        return {"status": "SUCCESS", "data": data}
    except SQLAlchemyError as e:
        logger.error(f"Database error: {str(e)}", exc_info=True)
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return {"status": "ERROR", "message": "Database operation failed"}
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return {"status": "ERROR", "message": "Internal Server Error"}


class PackageCreateRequest(BaseModel):
    type: str
    price: Decimal
    services: str


@photobox.post("/packages")
async def create_package(request: PackageCreateRequest, db: AsyncSession = Depends(get_db)):
    try:
        new_package = Package(id=str(uuid4()), type=request.type,
                              price=request.price, services=request.services)
        db.add(new_package)
        await db.commit()
        await db.refresh(new_package)
        return {"status": "SUCCESS", "data": {"id": new_package.id, "type": new_package.type, "price": new_package.price, "services": new_package.services.split(',') if new_package.services else []}}
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail={
                            "status": "ERROR", "message": str(e)})


@photobox.get("/packages")
async def get_all_packages(response: Response, db: AsyncSession = Depends(get_db)):
    try:
        query = select(Package)
        result = await db.execute(query)
        packages = result.scalars().all()
        if not packages:
            response.status_code = 404
            return {"status": "NOT_FOUND", "message": "No packages found"}
        data = [{"id": pkg.id, "type": pkg.type, "price": pkg.price, "services": pkg.services.split(
            ',') if pkg.services else []} for pkg in packages]
        return {"status": "SUCCESS", "data": data}
    except SQLAlchemyError as e:
        response.status_code = 500
        return {"status": "ERROR", "message": str(e)}
