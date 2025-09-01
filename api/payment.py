import hashlib
import base64
import os
import httpx
from pydantic import BaseModel
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, Request
from decimal import Decimal

# Helper imports dari photobox.py
from api.photobox import (
    _update_transaction_status_in_db,
    _get_transaction_by_order_id
)
from config.database import get_db
from config.settings import settings

router = APIRouter()

# --- Pydantic Model untuk Callback Midtrans ---
class MidtransCallbackPayload(BaseModel):
    transaction_time: str
    transaction_status: str
    transaction_id: str
    status_code: str
    signature_key: str
    order_id: str
    merchant_id: str
    gross_amount: str
    fraud_status: str
    payment_type: str

# --- Service untuk Mengelola Semua Logika Midtrans ---
class MidtransService:
    def __init__(self, server_key: str, is_production: bool):
        self.server_key = server_key
        self.is_production = is_production
        
        auth_string = base64.b64encode(f"{self.server_key}:".encode()).decode()
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_string}"
        }

    async def create_snap_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Membuat transaksi Snap (untuk Web)."""
        snap_url = "https://app.midtrans.com/snap/v1/transactions" if self.is_production else "https://app.sandbox.midtrans.com/snap/v1/transactions"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(snap_url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                error_details = e.response.json()
                raise HTTPException(status_code=e.response.status_code, detail=f"Midtrans Snap Error: {error_details.get('error_messages', [str(e)])}")

    async def create_qris_transaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Membuat transaksi Core API untuk pembayaran QRIS (untuk Flutter)."""
        base_url = "https://api.midtrans.com/v2" if self.is_production else "https://api.sandbox.midtrans.com/v2"
        charge_url = f"{base_url}/charge"
        
        payload['payment_type'] = 'qris'
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(charge_url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                error_details = e.response.json()
                raise HTTPException(status_code=e.response.status_code, detail=f"Midtrans Core API Error: {error_details.get('status_message', str(e))}")

    def verify_signature(self, payload: MidtransCallbackPayload) -> bool:
        """Memvalidasi signature key dari notifikasi callback."""
        signature_string = f"{payload.order_id}{payload.status_code}{payload.gross_amount}{self.server_key}"
        expected_signature = hashlib.sha512(signature_string.encode()).hexdigest()
        return expected_signature == payload.signature_key

# --- Inisialisasi Service ---
midtrans_service = MidtransService(
    server_key=settings.MIDTRANS_SERVER_KEY,
    is_production=settings.MIDTRANS_IS_PRODUCTION
)

# --- Endpoint Callback ---
@router.post("/midtrans/callback")
async def handle_midtrans_callback(request: Request, db: AsyncSession = Depends(get_db)):
    json_payload = await request.json()
    payload = MidtransCallbackPayload.parse_obj(json_payload)

    if not midtrans_service.verify_signature(payload):
        raise HTTPException(status_code=401, detail="Invalid signature")

    order_id = payload.order_id
    
    existing_transaction = await _get_transaction_by_order_id(db, order_id)
    if not existing_transaction:
        raise HTTPException(status_code=404, detail=f"Transaction with order_id {order_id} not found.")

    if existing_transaction.status == 'PAID':
        return {"status": "ok", "message": "Transaction already processed."}

    transaction_status = payload.transaction_status
    fraud_status = payload.fraud_status
    
    new_db_status = existing_transaction.status
    
    if transaction_status == "settlement" or (transaction_status == "capture" and fraud_status == "accept"):
        new_db_status = "PAID"
    elif transaction_status in ["cancel", "deny", "expire"]:
        new_db_status = "FAILED"
        
    if new_db_status != existing_transaction.status:
        await _update_transaction_status_in_db(
            db=db,
            reference=order_id, 
            new_status=new_db_status,
            amount_received=Decimal(payload.gross_amount.split('.')[0])
        )

    return {"status": "ok"}