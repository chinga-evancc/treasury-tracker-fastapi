from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
import uuid
from .models import InvestmentType, InvestmentStatus, PaymentType, PaymentStatus

# Base schemas
class BaseSchema(BaseModel):
    class Config:
        from_attributes = True

# User schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)

class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None

class UserResponse(UserBase):
    id: uuid.UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True

# Authentication schemas
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class TokenData(BaseModel):
    user_id: Optional[str] = None

class PasswordReset(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6, max_length=100)

# Investment schemas
class InvestmentBase(BaseModel):
    investment_type: InvestmentType
    description: Optional[str] = Field(None, max_length=500)
    face_value: Decimal = Field(..., gt=0)
    purchase_price: Decimal = Field(..., gt=0)
    annual_coupon_rate: Optional[Decimal] = Field(0.0000, ge=0, le=1)
    issue_date: Optional[date] = None
    purchase_date: date
    maturity_date: date

    @validator('maturity_date')
    def validate_maturity_date(cls, v, values):
        if 'purchase_date' in values and v <= values['purchase_date']:
            raise ValueError('Maturity date must be after purchase date')
        return v

    @validator('issue_date')
    def validate_issue_date(cls, v, values):
        if v and 'purchase_date' in values and v > values['purchase_date']:
            raise ValueError('Issue date must be before or equal to purchase date')
        return v

    @validator('annual_coupon_rate')
    def validate_coupon_rate(cls, v, values):
        if 'investment_type' in values:
            if values['investment_type'] == InvestmentType.TREASURY_NOTE and v <= 0:
                raise ValueError('Treasury notes must have a positive coupon rate')
            elif values['investment_type'] == InvestmentType.TREASURY_BILL and v != 0:
                raise ValueError('Treasury bills should not have a coupon rate')
        return v

class InvestmentCreate(InvestmentBase):
    pass

class InvestmentUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=500)
    status: Optional[InvestmentStatus] = None

class InvestmentResponse(InvestmentBase):
    id: uuid.UUID
    user_id: uuid.UUID
    status: InvestmentStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Payment Schedule schemas
class PaymentScheduleBase(BaseModel):
    payment_date: date
    payment_amount: Decimal = Field(..., gt=0)
    payment_type: PaymentType
    description: Optional[str] = Field(None, max_length=255)

class PaymentScheduleResponse(PaymentScheduleBase):
    id: uuid.UUID
    investment_id: uuid.UUID
    payment_status: PaymentStatus
    actual_payment_date: Optional[date] = None
    actual_payment_amount: Optional[Decimal] = None
    created_at: datetime

    class Config:
        from_attributes = True

class PaymentScheduleUpdate(BaseModel):
    payment_status: Optional[PaymentStatus] = None
    actual_payment_date: Optional[date] = None
    actual_payment_amount: Optional[Decimal] = Field(None, gt=0)

# Portfolio schemas
class PortfolioSummary(BaseModel):
    total_investments: int
    active_investments: int
    total_face_value: Decimal
    total_purchase_price: Decimal
    expected_returns: Decimal
    expected_profit: Decimal
    portfolio_yield: Decimal

class UpcomingPayment(BaseModel):
    id: uuid.UUID
    investment_id: uuid.UUID
    investment_description: Optional[str]
    investment_type: InvestmentType
    payment_date: date
    payment_amount: Decimal
    payment_type: PaymentType
    payment_status: PaymentStatus
    description: Optional[str]

    class Config:
        from_attributes = True

class InvestmentWithPayments(InvestmentResponse):
    payment_schedules: List[PaymentScheduleResponse] = []

class PortfolioResponse(BaseModel):
    summary: PortfolioSummary
    investments: List[InvestmentResponse]
    upcoming_payments: List[UpcomingPayment]

# Error schemas
class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None

class ValidationErrorResponse(BaseModel):
    detail: List[dict]
    error_code: str = "validation_error"

# Success schemas
class SuccessResponse(BaseModel):
    message: str
    data: Optional[dict] = None

