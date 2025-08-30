# api/tripay.py
import os
import httpx
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime, timedelta
from api.photobox import _save_transaction_to_db
from config.database import get_db
from config.settings import settings # <-- Path import sudah benar

router = APIRouter()

# ... (sisa kode sama persis seperti yang Anda berikan)
# FIX 3: Pastikan Pydantic models terdefinisi
class CreateTransactionRequest(BaseModel):
    method: str
    amount: int
    customer_name: str
    customer_email: str
    items: List[Dict[str, Any]]
    return_url: str

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
async def create_transaction(transaction_data: CreateTransactionRequest):
    merchant_ref = f"SELASAAT-{os.urandom(4).hex()}"
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
                headers={
                    "Authorization": f"Bearer {settings.TRIPAY_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            response.raise_for_status()
            tripay_response_json = response.json()
            
            # --- NEW: SAVE TO DATABASE ---
            # If the transaction was successfully created on Tripay's side...
            if tripay_response_json.get('success'):
                # ...save it to our own database in the background.
                await _save_transaction_to_db(
                    db=get_db(),
                    tripay_data=tripay_response_json.get('data', {}),
                    order_items=transaction_data.items
                )
            # ---------------------------

            # Return the original response from Tripay to the client
            return tripay_response_json
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Failed to create transaction")

### Endpoint 3: Mengatur Callback untuk Notifikasi Pembayaran
@router.post("/tripay/callback")
async def handle_callback(payload: CallbackPayload):
    signature_string = f"{payload.merchant_ref}{payload.reference}{payload.status}"
    
    expected_signature = hmac.new(
        settings.TRIPAY_PRIVATE_KEY.encode(), # <-- FIX 2: Diganti ke settings
        signature_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if payload.signature != expected_signature:
        raise HTTPException(status_code=403, detail="Invalid signature")

    if payload.status == "PAID":
        print(f"Transaksi {payload.merchant_ref} berhasil dibayar.")
    elif payload.status == "EXPIRED":
        print(f"Transaksi {payload.merchant_ref} kadaluarsa.")

    return {"success": True}