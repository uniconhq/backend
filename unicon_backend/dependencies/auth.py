from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from unicon_backend.helpers.constants import SECRET_KEY
from unicon_backend.models import User, engine


class OAuth2IgnoreError(OAuth2PasswordBearer):
    """Ignore HTTP error because we want to accept cookie auth too"""

    async def __call__(self, request: Request) -> str | None:
        try:
            return await super().__call__(request)
        except HTTPException:
            return ""


# This url = login post url
oauth2_scheme = OAuth2IgnoreError(tokenUrl="/auth/token")


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

##################
# Password utils #
##################

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str):
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str):
    with Session(engine) as session:
        user = session.scalars(select(User).where(User.username == username)).first()
        if not user:
            return False
        if not verify_password(password, user.password):
            return False
        return user


###############
#  JWT utils  #
###############


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


###################
# Auth dependency #
###################


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[str | None, Cookie()] = None,
):
    if (token := token or session) is None:
        raise Exception("No token")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id = payload.get("sub")
        with Session(engine) as db_session:
            user = db_session.get(User, id)
        if user is None:
            raise InvalidTokenError()
        return user

    except InvalidTokenError as invalid_token_err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from invalid_token_err
