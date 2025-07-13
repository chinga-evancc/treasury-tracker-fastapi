from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Enum as SQLEnum, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum
from .database import Base

# Enums
class InvestmentType(str, enum.Enum):
    TREASURY_NOTE = "treasury_note"
    TREASURY_BILL = "treasury_bill"

class InvestmentStatus(str, enum.Enum):
    ACTIVE = "active"
    MATURED = "matured"
    SOLD = "sold"
    CANCELLED = "cancelled"

class PaymentType(str, enum.Enum):
    COUPON = "coupon"
    PRINCIPAL = "principal"
    FINAL_PAYMENT = "final_payment"

class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    DUE = "due"
    PAID = "paid"
    OVERDUE = "overdue"

# User model
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, index=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    password_reset_token = Column(String(255))
    password_reset_expires = Column(DateTime(timezone=True))
    verification_token = Column(String(255))
    verification_expires = Column(DateTime(timezone=True))

    # Relationships
    investments = relationship("Investment", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")

# Investment model
class Investment(Base):
    __tablename__ = "investments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    investment_type = Column(SQLEnum(InvestmentType), nullable=False)
    description = Column(String(500))
    face_value = Column(Numeric(15, 2), nullable=False)
    purchase_price = Column(Numeric(15, 2), nullable=False)
    annual_coupon_rate = Column(Numeric(5, 4), default=0.0000)
    issue_date = Column(Date)
    purchase_date = Column(Date, nullable=False)
    maturity_date = Column(Date, nullable=False, index=True)
    status = Column(SQLEnum(InvestmentStatus), default=InvestmentStatus.ACTIVE, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="investments")
    payment_schedules = relationship("PaymentSchedule", back_populates="investment", cascade="all, delete-orphan")

# Payment Schedule model
class PaymentSchedule(Base):
    __tablename__ = "payment_schedules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    investment_id = Column(String(36), ForeignKey("investments.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_date = Column(Date, nullable=False, index=True)
    payment_amount = Column(Numeric(15, 2), nullable=False)
    payment_type = Column(SQLEnum(PaymentType), nullable=False)
    payment_status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    description = Column(String(255))
    actual_payment_date = Column(Date)
    actual_payment_amount = Column(Numeric(15, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    investment = relationship("Investment", back_populates="payment_schedules")

# User Session model
class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_accessed = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String(45))  # IPv6 max length
    user_agent = Column(Text)

    # Relationships
    user = relationship("User", back_populates="sessions")

# Audit Log model
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    table_name = Column(String(50), nullable=False)
    record_id = Column(String(36), nullable=False)
    action = Column(String(20), nullable=False)  # INSERT, UPDATE, DELETE
    old_values = Column(Text)  # JSON as text for SQLite
    new_values = Column(Text)  # JSON as text for SQLite
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String(45))  # IPv6 max length
    user_agent = Column(Text)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

