from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from unicon_backend.constants import SECRET_KEY
from unicon_backend.dependencies.auth import (
    AUTH_ALGORITHM,
    AUTH_PWD_CONTEXT,
    get_current_user,
    get_db_session,
)
from unicon_backend.models import UserORM
from unicon_backend.schemas.auth import Token, UserCreate, UserPublic

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

router = APIRouter(prefix="/auth", tags=["auth"])


def create_token(user: UserORM, response: Response):
    user_public = UserPublic.model_validate(user)
    access_token: str = jwt.encode(
        {
            "sub": str(user.id),
            "exp": datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        },
        SECRET_KEY,
        algorithm=AUTH_ALGORITHM,
    )
    response.set_cookie(
        key="session", value=access_token, samesite="none", secure=True, httponly=True
    )

    return Token(access_token=access_token, token_type="bearer", user=user_public)


@router.post("/token")
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db_session: Annotated[Session, Depends(get_db_session)],
    response: Response,
) -> Token:
    # NOTE: `password` is hashed
    username, password = form_data.username, form_data.password

    user: UserORM | None = db_session.scalars(
        select(UserORM).where(UserORM.username == username)
    ).first()
    if user is None or not AUTH_PWD_CONTEXT.verify(password, user.password):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED, detail="Incorrect username or password."
        )

    return create_token(user, response)


@router.post("/signup")
def signup(
    create_data: UserCreate,
    db_session: Annotated[Session, Depends(get_db_session)],
    response: Response,
) -> Token:
    username, password = create_data.username, create_data.password
    if db_session.exec(select(UserORM).where(UserORM.username == username)).first():
        raise HTTPException(HTTPStatus.BAD_REQUEST, "Username already exists")

    hashed_password = AUTH_PWD_CONTEXT.hash(password)

    new_user = UserORM(username=username, password=hashed_password)
    db_session.add(new_user)
    db_session.commit()
    db_session.refresh(new_user)

    return create_token(new_user, response)


@router.get("/logout")
def logout(response: Response):
    response.delete_cookie(key="session", samesite="none", secure=True, httponly=True)
    return ""


@router.get("/session")
def get_user(user: Annotated[UserORM, Depends(get_current_user)]) -> UserPublic:
    return UserPublic.model_validate(user)
