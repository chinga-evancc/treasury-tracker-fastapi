from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
import uuid

from ..database import get_db
from ..models import User, Investment, PaymentSchedule, InvestmentType, InvestmentStatus, PaymentStatus
from ..schemas import (
    InvestmentCreate, InvestmentUpdate, InvestmentResponse, InvestmentWithPayments,
    PaymentScheduleResponse, PaymentScheduleUpdate, PortfolioSummary, 
    PortfolioResponse, UpcomingPayment, SuccessResponse
)
from ..auth import get_current_user

router = APIRouter(prefix="/investments", tags=["Investments"])

def generate_payment_schedule(db: Session, investment: Investment):
    """Generate payment schedule for an investment."""
    # Clear existing payment schedules
    db.query(PaymentSchedule).filter(PaymentSchedule.investment_id == investment.id).delete()
    
    if investment.investment_type == InvestmentType.TREASURY_NOTE:
        # Calculate semi-annual coupon amount
        coupon_amount = (investment.face_value * investment.annual_coupon_rate) / 2
        
        # Generate semi-annual payments starting 6 months from issue date
        current_date = investment.issue_date
        payment_count = 0
        
        # Add 6 months for first payment
        from dateutil.relativedelta import relativedelta
        current_date = current_date + relativedelta(months=6)
        
        while current_date <= investment.maturity_date:
            payment_count += 1
            
            if current_date == investment.maturity_date:
                # Final payment includes coupon + principal
                payment = PaymentSchedule(
                    investment_id=investment.id,
                    payment_date=current_date,
                    payment_amount=coupon_amount + investment.face_value,
                    payment_type="final_payment",
                    description="Final coupon payment + Principal repayment"
                )
            else:
                # Regular coupon payment
                payment = PaymentSchedule(
                    investment_id=investment.id,
                    payment_date=current_date,
                    payment_amount=coupon_amount,
                    payment_type="coupon",
                    description=f"Semi-annual coupon payment #{payment_count}"
                )
            
            db.add(payment)
            
            # Move to next payment date (6 months later)
            current_date = current_date + relativedelta(months=6)
    
    elif investment.investment_type == InvestmentType.TREASURY_BILL:
        # Treasury bills have only one payment at maturity
        payment = PaymentSchedule(
            investment_id=investment.id,
            payment_date=investment.maturity_date,
            payment_amount=investment.face_value,
            payment_type="principal",
            description="Treasury bill maturity payment"
        )
        db.add(payment)
    
    db.commit()

@router.post("/", response_model=InvestmentResponse, status_code=status.HTTP_201_CREATED)
async def create_investment(
    investment_data: InvestmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new investment."""
    # Create investment
    db_investment = Investment(
        user_id=current_user.id,
        **investment_data.dict()
    )
    
    db.add(db_investment)
    db.commit()
    db.refresh(db_investment)
    
    # Generate payment schedule
    generate_payment_schedule(db, db_investment)
    
    return db_investment

@router.get("/", response_model=List[InvestmentResponse])
async def get_investments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[InvestmentStatus] = Query(None, description="Filter by investment status"),
    investment_type: Optional[InvestmentType] = Query(None, description="Filter by investment type"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return")
):
    """Get all investments for the current user."""
    query = db.query(Investment).filter(Investment.user_id == current_user.id)
    
    if status_filter:
        query = query.filter(Investment.status == status_filter)
    
    if investment_type:
        query = query.filter(Investment.investment_type == investment_type)
    
    investments = query.offset(skip).limit(limit).all()
    return investments

@router.get("/{investment_id}", response_model=InvestmentWithPayments)
async def get_investment(
    investment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific investment with payment schedules."""
    investment = db.query(Investment).filter(
        and_(Investment.id == investment_id, Investment.user_id == current_user.id)
    ).first()
    
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment not found"
        )
    
    # Get payment schedules
    payment_schedules = db.query(PaymentSchedule).filter(
        PaymentSchedule.investment_id == investment_id
    ).order_by(PaymentSchedule.payment_date).all()
    
    return {
        **investment.__dict__,
        "payment_schedules": payment_schedules
    }

@router.put("/{investment_id}", response_model=InvestmentResponse)
async def update_investment(
    investment_id: uuid.UUID,
    investment_update: InvestmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an investment."""
    investment = db.query(Investment).filter(
        and_(Investment.id == investment_id, Investment.user_id == current_user.id)
    ).first()
    
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment not found"
        )
    
    # Update fields
    update_data = investment_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(investment, field, value)
    
    db.commit()
    db.refresh(investment)
    
    return investment

@router.delete("/{investment_id}", response_model=SuccessResponse)
async def delete_investment(
    investment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an investment."""
    investment = db.query(Investment).filter(
        and_(Investment.id == investment_id, Investment.user_id == current_user.id)
    ).first()
    
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment not found"
        )
    
    db.delete(investment)
    db.commit()
    
    return {"message": "Investment successfully deleted"}

@router.get("/{investment_id}/payments", response_model=List[PaymentScheduleResponse])
async def get_payment_schedule(
    investment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    status_filter: Optional[PaymentStatus] = Query(None, description="Filter by payment status")
):
    """Get payment schedule for an investment."""
    # Verify investment ownership
    investment = db.query(Investment).filter(
        and_(Investment.id == investment_id, Investment.user_id == current_user.id)
    ).first()
    
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment not found"
        )
    
    query = db.query(PaymentSchedule).filter(PaymentSchedule.investment_id == investment_id)
    
    if status_filter:
        query = query.filter(PaymentSchedule.payment_status == status_filter)
    
    payments = query.order_by(PaymentSchedule.payment_date).all()
    return payments

@router.put("/{investment_id}/payments/{payment_id}", response_model=PaymentScheduleResponse)
async def update_payment(
    investment_id: uuid.UUID,
    payment_id: uuid.UUID,
    payment_update: PaymentScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a payment schedule entry."""
    # Verify investment ownership
    investment = db.query(Investment).filter(
        and_(Investment.id == investment_id, Investment.user_id == current_user.id)
    ).first()
    
    if not investment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment not found"
        )
    
    # Get payment
    payment = db.query(PaymentSchedule).filter(
        and_(
            PaymentSchedule.id == payment_id,
            PaymentSchedule.investment_id == investment_id
        )
    ).first()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )
    
    # Update fields
    update_data = payment_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(payment, field, value)
    
    db.commit()
    db.refresh(payment)
    
    return payment

@router.get("/portfolio/summary", response_model=PortfolioSummary)
async def get_portfolio_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get portfolio summary for the current user."""
    # Get all active investments
    investments = db.query(Investment).filter(
        and_(Investment.user_id == current_user.id, Investment.status == InvestmentStatus.ACTIVE)
    ).all()
    
    total_investments = len(investments)
    active_investments = total_investments
    total_face_value = sum(inv.face_value for inv in investments)
    total_purchase_price = sum(inv.purchase_price for inv in investments)
    
    # Calculate expected returns (sum of all pending/due payments)
    expected_returns = Decimal('0')
    for investment in investments:
        pending_payments = db.query(PaymentSchedule).filter(
            and_(
                PaymentSchedule.investment_id == investment.id,
                PaymentSchedule.payment_status.in_([PaymentStatus.PENDING, PaymentStatus.DUE])
            )
        ).all()
        expected_returns += sum(payment.payment_amount for payment in pending_payments)
    
    expected_profit = expected_returns - total_purchase_price
    portfolio_yield = (expected_profit / total_purchase_price * 100) if total_purchase_price > 0 else Decimal('0')
    
    return PortfolioSummary(
        total_investments=total_investments,
        active_investments=active_investments,
        total_face_value=total_face_value,
        total_purchase_price=total_purchase_price,
        expected_returns=expected_returns,
        expected_profit=expected_profit,
        portfolio_yield=portfolio_yield
    )

@router.get("/portfolio/upcoming-payments", response_model=List[UpcomingPayment])
async def get_upcoming_payments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days_ahead: int = Query(90, ge=1, le=365, description="Number of days to look ahead"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of payments to return")
):
    """Get upcoming payments for the user's portfolio."""
    end_date = date.today() + timedelta(days=days_ahead)
    
    payments = db.query(PaymentSchedule, Investment).join(
        Investment, PaymentSchedule.investment_id == Investment.id
    ).filter(
        and_(
            Investment.user_id == current_user.id,
            PaymentSchedule.payment_status.in_([PaymentStatus.PENDING, PaymentStatus.DUE]),
            PaymentSchedule.payment_date >= date.today(),
            PaymentSchedule.payment_date <= end_date
        )
    ).order_by(PaymentSchedule.payment_date).limit(limit).all()
    
    return [
        UpcomingPayment(
            id=payment.id,
            investment_id=payment.investment_id,
            investment_description=investment.description,
            investment_type=investment.investment_type,
            payment_date=payment.payment_date,
            payment_amount=payment.payment_amount,
            payment_type=payment.payment_type,
            payment_status=payment.payment_status,
            description=payment.description
        )
        for payment, investment in payments
    ]

@router.get("/portfolio/full", response_model=PortfolioResponse)
async def get_full_portfolio(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get complete portfolio information."""
    # Get portfolio summary
    summary = await get_portfolio_summary(current_user, db)
    
    # Get all investments
    investments = await get_investments(current_user, db)
    
    # Get upcoming payments
    upcoming_payments = await get_upcoming_payments(current_user, db)
    
    return PortfolioResponse(
        summary=summary,
        investments=investments,
        upcoming_payments=upcoming_payments
    )

