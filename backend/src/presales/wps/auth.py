from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from fastapi import Header, HTTPException
from sqlalchemy import select

from presales.storage import now

from .models import WpsAccessToken, WpsPairing

PAIRING_LIFETIME_MINUTES = 10


def secret_hash(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class WpsAuth:
    def __init__(self, session):
        self.session = session

    def issue_pairing(self, actor: str) -> str:
        code = token_urlsafe(18)
        self.session.add(
            WpsPairing(
                code_hash=secret_hash(code),
                actor=actor.strip(),
                expires_at=now() + timedelta(minutes=PAIRING_LIFETIME_MINUTES),
            )
        )
        self.session.flush()
        return code

    def exchange(self, code: str) -> dict:
        pairing = self.session.scalar(
            select(WpsPairing).where(WpsPairing.code_hash == secret_hash(code)).with_for_update()
        )
        if pairing is None or pairing.consumed_at is not None or utc(pairing.expires_at) <= now():
            raise ValueError("配对码无效、已使用或已过期")
        raw_token = token_urlsafe(32)
        access = WpsAccessToken(token_hash=secret_hash(raw_token), actor=pairing.actor)
        pairing.consumed_at = now()
        self.session.add(access)
        self.session.flush()
        return {"access_token": raw_token, "token_type": "bearer", "actor": pairing.actor}

    def authenticate(self, authorization: str | None) -> WpsAccessToken:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="请先连接售前工作台账号")
        raw_token = authorization.removeprefix("Bearer ").strip()
        access = self.session.scalar(
            select(WpsAccessToken).where(WpsAccessToken.token_hash == secret_hash(raw_token))
        )
        if access is None or access.revoked_at is not None:
            raise HTTPException(status_code=401, detail="插件登录已失效，请重新配对")
        access.last_used_at = now()
        return access

    def revoke(self, token_id: str) -> None:
        access = self.session.get(WpsAccessToken, token_id)
        if access is None:
            raise ValueError("访问令牌不存在")
        access.revoked_at = now()


def bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    return authorization
