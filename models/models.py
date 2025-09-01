# models.py

from sqlalchemy import (
    Column, String, Enum as SAEnum, ForeignKey, DECIMAL, Text, Integer, 
    TIMESTAMP, func, BigInteger
)
from sqlalchemy.orm import relationship
from config.database import Base

# ==============================================================================
# MODEL-MODEL TABEL BARU
# ==============================================================================

class Package(Base):
    __tablename__ = "Packages"

    id = Column(String(36), primary_key=True)
    type = Column(String(255), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    services = Column(Text, nullable=True) # Sesuai skema, ini TEXT dan boleh null

class Frame(Base):
    __tablename__ = "Frames"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    image_link = Column(Text, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    positions = relationship("FramePosition", back_populates="frame", cascade="all, delete-orphan")
    sessions = relationship("PhotoSession", back_populates="frame")

class FramePosition(Base):
    __tablename__ = "FramePositions"

    id = Column(String(36), primary_key=True)
    frame_id = Column(String(36), ForeignKey("Frames.id", ondelete="CASCADE"), nullable=False)
    x = Column(Integer, nullable=False, default=168)
    y = Column(Integer, nullable=False, default=680)
    width = Column(Integer, nullable=False, default=564)
    height = Column(Integer, nullable=False, default=439)

    frame = relationship("Frame", back_populates="positions")
    captures = relationship("Capture", back_populates="frame_position")

class Transaction(Base):
    __tablename__ = "Transactions"

    id = Column(String(36), primary_key=True)
    reference = Column(String(255), nullable=False, unique=True)
    merchant_ref = Column(String(255), nullable=False, unique=True)
    transaction_type = Column(SAEnum('PHOTOSESSION', 'VOUCHER', name='transaction_type_enum'), nullable=False)
    payment_method = Column(String(100), nullable=True)
    payment_name = Column(String(255), nullable=True)
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_phone = Column(String(50), nullable=True)
    amount = Column(DECIMAL(15, 2), nullable=False)
    amount_received = Column(DECIMAL(15, 2), server_default='0.00')
    checkout_url = Column(Text, nullable=True)
    status = Column(SAEnum('PENDING', 'PAID', 'EXPIRED', 'FAILED', name='transaction_status_enum'), nullable=False, server_default='PENDING')
    expired_time = Column(BigInteger, nullable=True)
    qr_string = Column(Text, nullable=True)
    qr_url = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    # Relasi baru
    order_items = relationship("OrderItem", back_populates="transaction", cascade="all, delete-orphan")
    sessions = relationship("PhotoSession", back_populates="transaction")
    vouchers = relationship("Voucher", back_populates="transaction")

class OrderItem(Base):
    __tablename__ = "OrderItems"

    id = Column(String(36), primary_key=True)
    transaction_id = Column(String(36), ForeignKey("Transactions.id", ondelete="CASCADE"), nullable=False)
    package_id = Column(String(36), ForeignKey("Packages.id", ondelete="RESTRICT"), nullable=False)
    item_name = Column(String(255), nullable=False)
    item_price = Column(DECIMAL(15, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    
    transaction = relationship("Transaction", back_populates="order_items")
    package = relationship("Package")

class Voucher(Base):
    __tablename__ = "Vouchers"
    
    id = Column(String(36), primary_key=True)
    package_id = Column(String(36), ForeignKey("Packages.id", ondelete="CASCADE"), nullable=False)
    transaction_id = Column(String(36), ForeignKey("Transactions.id", ondelete="RESTRICT"), nullable=False)
    code = Column(String(255), unique=True, nullable=True)
    recipient_email = Column(String(255), nullable=True)
    status = Column(SAEnum('PENDING_PAYMENT', 'ACTIVE', 'USED', 'REVOKED', name='voucher_status_enum'), nullable=False, server_default='PENDING_PAYMENT')
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    package = relationship("Package")
    transaction = relationship("Transaction", back_populates="vouchers")

# models.py (Bagian yang perlu diperbaiki)

class PhotoSession(Base):
    __tablename__ = "PhotoSessions"

    id = Column(String(36), primary_key=True)
    transaction_id = Column(String(36), ForeignKey("Transactions.id", ondelete="CASCADE"), nullable=False)
    frame_id = Column(String(36), ForeignKey("Frames.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    recipient_email = Column(String(255), nullable=True)
    image_filter = Column(String(255), nullable=True)
    result_image_url = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    
    transaction = relationship("Transaction", back_populates="sessions")
    frame = relationship("Frame", back_populates="sessions")
    captures = relationship("Capture", back_populates="session", cascade="all, delete-orphan")

class Capture(Base):
    __tablename__ = "Captures"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("PhotoSessions.id", ondelete="CASCADE"), nullable=False)
    normal_capture_url = Column(Text, nullable=False)
    raw_capture_url = Column(Text, nullable=False)
    frame_position_id = Column(String(36), ForeignKey("FramePositions.id", ondelete="SET NULL"), nullable=True)

    session = relationship("PhotoSession", back_populates="captures")
    frame_position = relationship("FramePosition", back_populates="captures")