"""/api/auth — app-level owner login (Fallout-styled UI, no native browser popup)."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from app.core import webauth

router = APIRouter(prefix="/api/auth")


class LoginIn(BaseModel):
    login: str
    password: str


@router.post("/login")
async def login(body: LoginIn, response: Response):
    if not webauth.verify(body.login.strip(), body.password):
        return {"ok": False, "reason": "ДОСТУП ЗАПРЕЩЁН — неверный логин или пароль"}
    token = webauth.issue(body.login.strip())
    response.set_cookie(webauth.COOKIE, token, max_age=webauth.TOKEN_TTL,
                        httponly=True, samesite="lax", secure=True, path="/")
    return {"ok": True, "login": body.login.strip()}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(webauth.COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    lg = webauth.valid(request.cookies.get(webauth.COOKIE))
    return {"authed": bool(lg), "login": lg}
