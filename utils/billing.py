from datetime import datetime, timedelta
from app.models import db

def refresh_user_credits(user):
    """Refreshes credits to 3 if the last reset was more than 24 hours ago."""
    if user.is_pro:
        user.credits_remaining = 9999  # Unlimited for Pro
        return True

    now = datetime.utcnow()
    # Check if we are in a different calendar day than the last reset
    if user.last_credit_reset is None or now.date() > user.last_credit_reset.date():
        user.credits_remaining = 3
        user.last_credit_reset = now
        db.session.commit()
        return True
    return False

def can_process(user):
    """Checks if a user has sufficient credits to perform an action."""
    refresh_user_credits(user)
    return user.is_pro or user.credits_remaining > 0

def spend_credit(user):
    """Deducts one credit from the user's balance."""
    if user.is_pro:
        return True
        
    if user.credits_remaining > 0:
        user.credits_remaining -= 1
        db.session.commit()
        return True
    return False
