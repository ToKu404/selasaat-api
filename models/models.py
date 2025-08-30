from sqlalchemy import (
    Column, String, Enum as SAEnum, ForeignKey, DECIMAL, Text, Integer, 
    LargeBinary, TIMESTAMP, func, DateTime, BigInteger
)
from sqlalchemy.orm import relationship
from config.database import Base
from datetime import datetime
from enum import Enum as PyEnum

# Enum ini tidak digunakan di skema DB, tapi saya biarkan jika Anda memerlukannya di logika aplikasi
class FilterType(str, PyEnum):
    BLACK_AND_WHITE = "BLACK_AND_WHITE"
    PURPLE = "PURPLE"
    CYAN = "CYAN"
    OLD_TIMES = "OLD_TIMES"

# ==============================================================================
# MODEL-MODEL TABEL
# ==============================================================================

class Package(Base):
    __tablename__ = "Package"

    id = Column(String(36), primary_key=True)
    type = Column(String(255), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    # Diperbaiki: Sesuai skema, kolom ini tidak boleh null
    services = Column(String(255), nullable=False)

    sessions = relationship("PhotoSession", back_populates="package")

class Frame(Base):
    __tablename__ = "Frame"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    image_link = Column(Text, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    sessions = relationship("PhotoSession", back_populates="frame")
    positions = relationship("FramePosition", back_populates="frame", cascade="all, delete-orphan")

class FramePosition(Base):
    __tablename__ = "FramePosition"

    id = Column(String(36), primary_key=True)
    # Ditambahkan ondelete="CASCADE" untuk mencerminkan perilaku skema SQL
    frame_id = Column(String(36), ForeignKey("Frame.id", ondelete="CASCADE"), nullable=False)
    x = Column(Integer, nullable=False, default=168)
    y = Column(Integer, nullable=False, default=680)
    width = Column(Integer, nullable=False, default=564)
    height = Column(Integer, nullable=False, default=439)

    frame = relationship("Frame", back_populates="positions")

class Transaction(Base):
    __tablename__ = "Transactions"

    id = Column(String(36), primary_key=True)
    reference = Column(String(255), nullable=False, unique=True)
    merchant_ref = Column(String(255), nullable=True)
    payment_method = Column(String(100), nullable=False)
    payment_name = Column(String(255), nullable=False)
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_phone = Column(String(50), nullable=True)
    amount = Column(DECIMAL(15, 2), nullable=False)
    amount_received = Column(DECIMAL(15, 2), nullable=False)
    checkout_url = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    expired_time = Column(BigInteger, nullable=False)
    qr_string = Column(Text, nullable=True)
    qr_url = Column(Text, nullable=True)
    
    # Kolom Order Item
    order_item_name = Column(String(255), nullable=False)
    order_item_price = Column(DECIMAL(15, 2), nullable=False)
    order_item_quantity = Column(Integer, nullable=False)
    order_item_sku = Column(String(100), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relasi one-to-one ke Payment
    payment = relationship("Payment", back_populates="transaction", uselist=False, cascade="all, delete-orphan")

class Payment(Base):
    __tablename__ = "Payments"

    id = Column(String(36), primary_key=True)
    payment_method = Column(String(50), nullable=False)
    payment_status = Column(SAEnum("pending", "completed", "failed", name="payment_status_enum"), nullable=False)
    total_payment = Column(DECIMAL(10, 2), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    
    # Kunci Asing ke Transactions
    transaction_id = Column(String(36), ForeignKey("Transactions.id", ondelete="SET NULL"), nullable=True)
    
    # Relasi back-reference ke Transaction
    transaction = relationship("Transaction", back_populates="payment")
    sessions = relationship("PhotoSession", back_populates="payment")

class PhotoSession(Base):
    __tablename__ = "PhotoSession"

    session_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    result_image = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Kunci Asing
    payment_id = Column(String(36), ForeignKey("Payments.id", ondelete="SET NULL"), nullable=True)
    frame_id = Column(String(36), ForeignKey("Frame.id", ondelete="SET NULL"), nullable=True)
    package_id = Column(String(36), ForeignKey("Package.id", ondelete="SET NULL"), nullable=True)

    # Relasi
    payment = relationship("Payment", back_populates="sessions")
    frame = relationship("Frame", back_populates="sessions")
    package = relationship("Package", back_populates="sessions")
    captures = relationship("Capture", back_populates="session", cascade="all, delete-orphan")

class Capture(Base):
    __tablename__ = "Captures"

    capture_id = Column(String(36), primary_key=True)
    image = Column(LargeBinary, nullable=False)
    
    # Kunci Asing ke PhotoSession
    session_id = Column(String(36), ForeignKey("PhotoSession.session_id", ondelete="CASCADE"), nullable=False)
    
    # Relasi
    session = relationship("PhotoSession", back_populates="captures")