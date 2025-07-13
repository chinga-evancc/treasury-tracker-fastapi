from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional
import uuid

from ..database import get_db
from ..models import User, UserSession
from ..schemas import (
    UserCreate, UserLogin, UserResponse, Token, 
    PasswordReset, PasswordResetConfirm, SuccessResponse, ErrorResponse
)
from ..auth import (
    authenticate_user, create_access_token, get_password_hash, 
    get_current_user, create_user_session, revoke_user_session,
    revoke_all_user_sessions, generate_reset_token, verify_password
)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Register a new user."""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        full_name=user_data.full_name,
        is_verified=True  # Auto-verify for demo purposes
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@router.post("/login", response_model=Token)
async def login_user(
    user_credentials: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    """Authenticate user and return access token."""
    user = authenticate_user(db, user_credentials.email, user_credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is deactivated"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=30 * 24 * 60)  # 30 days
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    
    # Create user session
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    create_user_session(db, user.id, access_token, ip_address, user_agent)
    
    # Update last login
    user.last_login = datetime.utcnow()
    db.commit()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int(access_token_expires.total_seconds()),
        "user": user
    }

@router.post("/logout", response_model=SuccessResponse)
async def logout_user(
    current_user: User = Depends(get_current_user),
    credentials = Depends(security),
    db: Session = Depends(get_db)
):
    """Logout user and revoke current session."""
    token = credentials.credentials
    revoked = revoke_user_session(db, token)
    
    if revoked:
        return {"message": "Successfully logged out"}
    else:
        return {"message": "Session already expired or invalid"}

@router.post("/logout-all", response_model=SuccessResponse)
async def logout_all_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Logout user from all sessions."""
    revoked_count = revoke_all_user_sessions(db, current_user.id)
    return {"message": f"Successfully logged out from {revoked_count} sessions"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user

@router.post("/forgot-password", response_model=SuccessResponse)
async def forgot_password(
    password_reset: PasswordReset,
    db: Session = Depends(get_db)
):
    """Request password reset token."""
    user = db.query(User).filter(User.email == password_reset.email).first()
    
    # Always return success to prevent email enumeration
    if user:
        # Generate reset token
        reset_token = generate_reset_token()
        user.password_reset_token = reset_token
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        
        # In a real application, you would send an email here
        # For demo purposes, we'll just log the token
        print(f"Password reset token for {user.email}: {reset_token}")
    
    return {"message": "If the email exists, a password reset link has been sent"}

@router.post("/reset-password", response_model=SuccessResponse)
async def reset_password(
    password_reset_confirm: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """Reset password using reset token."""
    user = db.query(User).filter(
        User.password_reset_token == password_reset_confirm.token,
        User.password_reset_expires > datetime.utcnow()
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Update password
    user.password_hash = get_password_hash(password_reset_confirm.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    
    # Revoke all existing sessions
    revoke_all_user_sessions(db, user.id)
    
    db.commit()
    
    return {"message": "Password successfully reset"}

@router.post("/change-password", response_model=SuccessResponse)
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user password."""
    # Verify current password
    if not verify_password(current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # Update password
    current_user.password_hash = get_password_hash(new_password)
    
    # Revoke all other sessions (keep current session active)
    db.query(UserSession).filter(
        UserSession.user_id == current_user.id
    ).delete()
    
    db.commit()
    
    return {"message": "Password successfully changed"}

@router.get("/sessions", response_model=list)
async def get_user_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active sessions for the current user."""
    sessions = db.query(UserSession).filter(
        UserSession.user_id == current_user.id,
        UserSession.expires_at > datetime.utcnow()
    ).all()
    
    return [
        {
            "id": str(session.id),
            "created_at": session.created_at,
            "last_accessed": session.last_accessed,
            "expires_at": session.expires_at,
            "ip_address": str(session.ip_address) if session.ip_address else None,
            "user_agent": session.user_agent
        }
        for session in sessions
    ]

@router.delete("/sessions/{session_id}", response_model=SuccessResponse)
async def revoke_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke a specific session."""
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    db.delete(session)
    db.commit()
    
    return {"message": "Session successfully revoked"}

