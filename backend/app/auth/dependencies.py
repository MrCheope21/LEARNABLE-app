from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.core.errors import AuthenticationError
from app.db.session import get_db
from app.models.user import User

# HTTPBearer (not OAuth2PasswordBearer): login takes a JSON body, so there's no OAuth2 password
# form for Swagger to post to — its "Authorize" dialog instead asks for the token directly.
# auto_error=False so a missing header gets our 401 envelope rather than FastAPI's default.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    claims = decode_access_token(credentials.credentials)
    user = db.get(User, claims[0]) if claims is not None else None
    # A token from before the latest password change is no longer valid.
    if user is None or claims is None or claims[1] != user.token_version:
        raise AuthenticationError("Invalid or expired token")
    return user
