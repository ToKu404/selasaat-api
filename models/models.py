from sqlalchemy import Column, String, Enum, ForeignKey, DECIMAL, Text, Integer, LargeBinary, TIMESTAMP, func, DateTime
from sqlalchemy.orm import relationship
from config.database import Base
from datetime import datetime
from enum import Enum as PyEnum

from config.database import Base # Impor dari lokasi baru


class FilterType(str, PyEnum):
    BLACK_AND_WHITE = "BLACK_AND_WHITE"
    PURPLE = "PURPLE"
    CYAN = "CYAN"
    OLD_TIMES = "OLD_TIMES"


# Tabel Package
class Package(Base):
    __tablename__ = "Package"

    id = Column(String(36), primary_key=True)
    type = Column(String(255), nullable=False)
    price = Column(DECIMAL(10, 2), nullable=False)
    services = Column(String(255), nullable=True)

    sessions = relationship("PhotoSession", back_populates="package")


# Tabel Frame
class Frame(Base):
    __tablename__ = "Frame"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    image_link = Column(Text, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now())

    sessions = relationship("PhotoSession", back_populates="frame")
    positions = relationship(
        "FramePosition", back_populates="frame", cascade="all, delete")


# Tabel FramePosition
class FramePosition(Base):
    __tablename__ = "FramePosition"

    id = Column(String(36), primary_key=True)
    frame_id = Column(String(36), ForeignKey("Frame.id"), nullable=False)
    x = Column(Integer, nullable=False, default=168)
    y = Column(Integer, nullable=False, default=680)
    width = Column(Integer, nullable=False, default=564)
    height = Column(Integer, nullable=False, default=439)

    frame = relationship("Frame", back_populates="positions")


# Tabel Payments
class Payment(Base):
    __tablename__ = "Payments"

    id = Column(String(36), primary_key=True)
    payment_method = Column(String(50), nullable=False)
    payment_status = Column(
        Enum("pending", "completed", "failed", name="payment_status"), nullable=False)
    total_payment = Column(DECIMAL(10, 2), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    sessions = relationship("PhotoSession", back_populates="payment")


# Tabel PhotoSession
class PhotoSession(Base):
    __tablename__ = "PhotoSession"

    session_id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    payment_id = Column(String(36), ForeignKey("Payments.id"), nullable=True)
    frame_id = Column(String(36), ForeignKey("Frame.id"), nullable=True)
    package_id = Column(String(36), ForeignKey("Package.id"), nullable=True)
    result_image = Column(LargeBinary, nullable=True)
    payment = relationship("Payment", back_populates="sessions")
    frame = relationship("Frame", back_populates="sessions")
    package = relationship("Package", back_populates="sessions")
    created_at = Column(DateTime, default=datetime.now,
                        nullable=False)  # Tambahan
