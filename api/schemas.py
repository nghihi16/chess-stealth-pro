from typing import Literal, Optional
from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    key: str = Field(..., min_length=4, max_length=64, description="Mã License Key")
    hwid: str = Field(..., min_length=4, max_length=128, description="Mã định danh phần cứng HWID")
    app_version: str = Field(default="2.0.0", max_length=32, description="Phiên bản ứng dụng")
    nonce: str = Field(default="", max_length=64, description="Chuỗi ngẫu nhiên chống Replay Attack")


class ActivateRequest(BaseModel):
    key: str = Field(..., min_length=4, max_length=64, description="Mã License Key cần kích hoạt")
    hwid: str = Field(..., min_length=4, max_length=128, description="Mã định danh phần cứng HWID gắn lần đầu")
    app_version: str = Field(default="2.0.0", max_length=32, description="Phiên bản ứng dụng")
    nonce: str = Field(default="", max_length=64, description="Chuỗi ngẫu nhiên chống Replay Attack")


class SignedLicenseResponse(BaseModel):
    valid: bool
    key: str
    type: Optional[Literal["trial_24h", "monthly", "lifetime"]] = None
    status: str
    hwid: Optional[str] = None
    expires_at: Optional[int] = None
    message: str
    server_time: int
    nonce: str
    signature: str = Field(..., description="Chữ ký số Ed25519 (128 hex chars) của phản hồi")


class ResetHwidRequest(BaseModel):
    key: str = Field(..., min_length=4, max_length=64)
    old_hwid: str = Field(..., min_length=4, max_length=128)
    new_hwid: str = Field(..., min_length=4, max_length=128)


class ResetHwidResponse(BaseModel):
    success: bool
    key: str
    new_hwid: Optional[str] = None
    reset_count: int
    remaining_resets_this_month: int
    message: str


class ClaimFreeKeyRequest(BaseModel):
    hwid: Optional[str] = Field(default=None, max_length=128)
    shortener_token: Optional[str] = Field(
        default=None, description="Token callback trả về từ Work.ink / Linkvertise / Lootlabs"
    )


class ClaimFreeKeyResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    claim_url: Optional[str] = None
    shortened_url: Optional[str] = None
    key: Optional[str] = None
    expires_at: Optional[int] = None
    message: str
