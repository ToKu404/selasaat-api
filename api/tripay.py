import hashlib
import hmac
import os
import httpx
from pydantic import BaseModel
from typing import List, Dict, Any, Literal
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, Request
from decimal import Decimal

# PERBARUI IMPORT HELPER
from api.photobox import _save_transaction_to_db, _update_transaction_status_in_db
from config.database import get_db
from config.settings import settings

router = APIRouter()

# Perbarui Pydantic Model untuk menerima transaction_type
class CreateTransactionRequest(BaseModel):
    method: str
    amount: int
    customer_name: str
    customer_email: str
    items: List[Dict[str, Any]]
    return_url: str
    transaction_type: Literal['PHOTOSESSION', 'VOUCHER'] # WAJIB DIISI DARI FRONTEND


class CallbackPayload(BaseModel):
    merchant_ref: str
    reference: str
    status: str
    signature: str

## Endpoint untuk Integrasi Tripay

### Endpoint 1: Mengambil Daftar Metode Pembayaran
@router.get("/tripay/channels")
async def get_payment_channels():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                settings.TRIPAY_API_URL + "merchant/payment-channel",
                headers={"Authorization": f"Bearer {settings.TRIPAY_API_KEY}"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to fetch payment channels")

### Endpoint 2: Membuat Transaksi Pembayaran
@router.post("/tripay/create-transaction")
async def create_transaction(transaction_data: CreateTransactionRequest, db: AsyncSession = Depends(get_db)):
    merchant_ref = f"SELASAAT-{os.urandom(4).hex().upper()}"
    signature_string = f"{settings.TRIPAY_MERCHANT_CODE}{merchant_ref}{transaction_data.amount}"

    signature = hmac.new(
        settings.TRIPAY_PRIVATE_KEY.encode(),
        signature_string.encode(),
        hashlib.sha256
    ).hexdigest()

    expired_time = int((datetime.utcnow() + timedelta(minutes=10)).timestamp())

    payload = {
        "method": transaction_data.method,
        "merchant_ref": merchant_ref,
        "amount": transaction_data.amount,
        "customer_name": transaction_data.customer_name,
        "customer_email": transaction_data.customer_email,
        "order_items": transaction_data.items,
        "return_url": transaction_data.return_url,
        "signature": signature,
        "expired_time": expired_time
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                settings.TRIPAY_API_URL + "transaction/create",
                json=payload,
                headers={"Authorization": f"Bearer {settings.TRIPAY_API_KEY}"}
            )
            response.raise_for_status()
            tripay_response_json = response.json()
            
            if tripay_response_json.get('success'):
                await _save_transaction_to_db(
                    db=db,
                    tripay_data=tripay_response_json.get('data', {}),
                    order_items=transaction_data.items,
                    transaction_type=transaction_data.transaction_type # Lewatkan tipe transaksi
                )

            return tripay_response_json
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            # Jika _save_transaction_to_db gagal, error akan ditangkap di sini
            raise HTTPException(status_code=500, detail=f"Gagal membuat transaksi: {str(e)}")


### Endpoint 3: Mengatur Callback untuk Notifikasi Pembayaran
### Endpoint 3: Mengatur Callback untuk Notifikasi Pembayaran
@router.post("/tripay/callback")
async def handle_callback(request: Request, db: AsyncSession = Depends(get_db)):
    # Validasi signature dari header, bukan body
    callback_signature = request.headers.get('X-Callback-Signature')
    json_payload = await request.json()
    
    private_key = settings.TRIPAY_PRIVATE_KEY
    signature = hmac.new(private_key.encode(), (await request.body()), hashlib.sha256).hexdigest()

    if signature != callback_signature:
        return HTTPException(status_code=401, detail='Invalid signature')
    
    # Ambil data dari payload JSON
    reference = json_payload.get('reference')
    status = json_payload.get('status')
    amount_received = Decimal(str(json_payload.get('total_amount', 0)))

    if not reference or not status:
        return HTTPException(status_code=400, detail='Payload tidak valid')
        
    # Panggil fungsi update yang baru
    await _update_transaction_status_in_db(
        db=db,
        reference=reference,
        new_status=status,
        amount_received=amount_received
    )

    return {"success": True}