# models.py

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class User:
    id: int
    first_name: str
    last_name: str
    email: str
    password_hash: str
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: tuple) -> "User":
        return cls(*row)

    def to_dict(self, include_password=False) -> Dict[str, Any]:
        user_dict = {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        if include_password:
            user_dict["password_hash"] = self.password_hash
        return user_dict

@dataclass
class PasswordResetToken:
    id: int
    user_id: int
    token: str
    expires_at: str
    is_used: bool
    created_at: str

    @classmethod
    def from_row(cls, row: tuple) -> "PasswordResetToken":
        return cls(*row)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "token": self.token,
            "expires_at": self.expires_at,
            "is_used": self.is_used,
            "created_at": self.created_at
        }
