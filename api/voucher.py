# api/vouchers.py

import logging
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from config.database import get_db
from models.models import Package, Transaction, Voucher
# Import fungsi dari tripay.py untuk membuat transaksi
from api.tripay import create_transaction as create_tripay_transaction
from api.tripay import CreateTransactionRequest as TripayCreateRequest

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Pydantic Models ---
class VoucherRequest(BaseModel):
    package_id: str
    recipient_email: str

class VoucherStatusResponse(BaseModel):
    status: str
    code: str | None = None
    package_type: str
    checkout_url: str | None = None


# --- Endpoint ---

@router.post("/vouchers/request")
async def request_voucher(request: VoucherRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    """
    Langkah 1: Pengguna me-request voucher. 
    Fungsi ini akan membuat transaksi di Tripay dan menyimpan record awal di database.
    """
    # 1. Validasi package
    package_result = await db.execute(select(Package).filter_by(id=request.package_id))
    package = package_result.scalars().first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    # 2. Siapkan data untuk membuat transaksi di Tripay
    # URL di frontend tempat pengguna akan diarahkan setelah pembayaran
    return_url = f"{http_request.base_url}static/voucher-success.html"
    
    tripay_request = TripayCreateRequest(
        method="QRISC", # Asumsi menggunakan QRIS, bisa diganti
        amount=int(package.price),
        customer_name="Voucher Recipient", # Bisa dibuat lebih dinamis
        customer_email=request.recipient_email,
        items=[{
            "sku": package.id,
            "name": f"Voucher Photobooth - {package.type}",
            "price": int(package.price),
            "quantity": 1
        }],
        return_url=return_url,
        transaction_type='VOUCHER'
    )

    try:
        # 3. Panggil fungsi create_transaction dari tripay.py
        tripay_response = await create_tripay_transaction(tripay_request, db)

        if not tripay_response.get('success'):
            raise HTTPException(status_code=500, detail=tripay_response.get('message', "Failed to create Tripay transaction."))

        # 4. Ambil merchant_ref dari respons untuk polling status
        merchant_ref = tripay_response['data']['merchant_ref']
        return {"status": "PENDING", "merchant_ref": merchant_ref}

    except HTTPException as e:
        # Re-raise HTTPException
        raise e
    except Exception as e:
        logger.error(f"Error requesting voucher: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while requesting the voucher.")


@router.get("/vouchers/status/{merchant_ref}")
async def get_voucher_status(merchant_ref: str, db: AsyncSession = Depends(get_db)):
    """
    Langkah 2: Frontend melakukan polling ke endpoint ini untuk cek status pembayaran.
    """
    # Cari transaksi berdasarkan merchant_ref
    tx_result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.vouchers).selectinload(Voucher.package))
        .filter_by(merchant_ref=merchant_ref)
    )
    transaction = tx_result.scalars().first()

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    if transaction.status == 'PAID':
        # Jika sudah dibayar, voucher pasti sudah aktif
        voucher = transaction.vouchers[0] if transaction.vouchers else None
        if voucher and voucher.status == 'ACTIVE':
            return VoucherStatusResponse(
                status="SUCCESS",
                code=voucher.code,
                package_type=voucher.package.type,
                checkout_url=None
            )
        else:
            # Kasus langka jika webhook belum selesai proses
            return VoucherStatusResponse(status="PROCESSING", code=None, package_type="", checkout_url=None)
            
    elif transaction.status in ['EXPIRED', 'FAILED']:
         return VoucherStatusResponse(status="FAILED", code=None, package_type="", checkout_url=None)

    else: # Status PENDING
        return VoucherStatusResponse(
            status="PENDING",
            code=None,
            package_type="",
            checkout_url=transaction.qr_url # <-- INI PERBAIKANNYA
        )