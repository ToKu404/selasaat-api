import os
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from config.database import get_db
from models.models import Package, Transaction, Voucher

# Import service Midtrans dan helper DB
from api.payment import midtrans_service
from api.photobox import _save_transaction_to_db

router = APIRouter()
logger = logging.getLogger(__name__)

# --- Pydantic Models ---
class VoucherRequest(BaseModel):
    package_id: str
    recipient_email: str

class VoucherStatusResponse(BaseModel):
    status: str
    code: str | None = None
    package_type: str | None = None
    checkout_url: str | None = None

# --- Endpoint ---

async def _create_voucher_transaction(request: VoucherRequest, db: AsyncSession, method: str):
    package_result = await db.execute(select(Package).filter_by(id=request.package_id))
    package = package_result.scalars().first()
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")

    order_id = f"VCR-{os.urandom(4).hex().upper()}"
    
    try:
        db_transaction_data = {
            "merchant_ref": order_id,
            "amount": int(package.price),
            "status": "PENDING",
            "customer_email": request.recipient_email,
            "customer_name": "Voucher Recipient",
            "transaction_type": 'VOUCHER'
        }
        order_items = [{
            "id": package.id, "price": int(package.price), "quantity": 1,
            "name": f"Voucher Photobooth - {package.type}"
        }]

        if method == 'snap':
            payload = {
                "transaction_details": {"order_id": order_id, "gross_amount": int(package.price)},
                "item_details": order_items,
                "customer_details": {"email": request.recipient_email, "first_name": "Voucher Recipient"}
            }
            midtrans_response = await midtrans_service.create_snap_transaction(payload)
            db_transaction_data.update({
                "reference": midtrans_response.get("token"),
                "checkout_url": midtrans_response.get("redirect_url"),
                "payment_method": "MIDTRANS_SNAP", "payment_name": "Midtrans Snap"
            })
            response_to_frontend = {"order_id": order_id, "redirect_url": midtrans_response.get("redirect_url")}
        
        elif method == 'qris':
            payload = {"transaction_details": {"order_id": order_id, "gross_amount": int(package.price)}}
            midtrans_response = await midtrans_service.create_qris_transaction(payload)
            qr_string = midtrans_response.get('qr_string')
            qr_url = next((a['url'] for a in midtrans_response.get('actions', []) if a['name'] == 'generate-qr-code'), None)
            db_transaction_data.update({
                "reference": midtrans_response.get("transaction_id"),
                "payment_method": "qris", "payment_name": "QRIS",
                "qr_string": qr_string, "qr_url": qr_url
            })
            response_to_frontend = {"order_id": order_id, "qr_string": qr_string, "qr_url": qr_url}

        await _save_transaction_to_db(db=db, tripay_data=db_transaction_data, order_items=order_items, transaction_type='VOUCHER')
        
        return response_to_frontend
        
    except Exception as e:
        logger.error(f"Error requesting voucher with method {method}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vouchers/request-snap")
async def request_voucher_snap(request: VoucherRequest, db: AsyncSession = Depends(get_db)):
    """Endpoint untuk Web (HTML) yang menggunakan Midtrans Snap."""
    return await _create_voucher_transaction(request, db, 'snap')

@router.post("/vouchers/request-qris")
async def request_voucher_qris(request: VoucherRequest, db: AsyncSession = Depends(get_db)):
    """Endpoint untuk Flutter yang meminta data QRIS secara langsung."""
    return await _create_voucher_transaction(request, db, 'qris')

@router.get("/vouchers/status/{order_id}")
async def get_voucher_status(order_id: str, db: AsyncSession = Depends(get_db)):
    """Endpoint untuk polling status pembayaran dari frontend."""
    tx_result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.vouchers).selectinload(Voucher.package))
        .filter_by(merchant_ref=order_id)
    )
    transaction = tx_result.scalars().first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    if transaction.status == 'PAID':
        voucher = transaction.vouchers[0] if transaction.vouchers else None
        return VoucherStatusResponse(
            status="SUCCESS",
            code=voucher.code if voucher else None,
            package_type=voucher.package.type if voucher and voucher.package else None
        )
    elif transaction.status in ['EXPIRED', 'FAILED']:
        return VoucherStatusResponse(status="FAILED")
    else: # PENDING
        return VoucherStatusResponse(status="PENDING", checkout_url=transaction.checkout_url)