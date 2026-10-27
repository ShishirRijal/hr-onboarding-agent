from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String, create_engine, delete, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from interactions.store import add_missing_columns, as_utc, database_url_from_env, ensure_sqlite_directory

ROLE_EMPLOYEE = "employee"
ROLE_HR = "hr"
REMOTE_OFFICE = "Remote"
SESSION_LIFETIME = timedelta(days=7)
# scrypt cost: n=2**14, r=8, p=1 is the commonly recommended minimum for interactive sign-in.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), index=True)
    job_title: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(80))
    # "Tallinn", "Tampere", "Porto", or "Remote" for people who work fully remotely.
    office: Mapped[str] = mapped_column(String(40))
    # The country they are employed in, which sets their leave, pay and holidays. Remote
    # work doesn't change it (Employee Handbook, Remote Work Policy).
    country: Mapped[str] = mapped_column(String(40))
    manager_name: Mapped[str | None] = mapped_column(String(120))
    start_date: Mapped[date] = mapped_column(Date)
    pronouns: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def employee_context(self) -> dict[str, str]:
        """Who is asking, for the agent: where they work decides which country's rules apply."""
        return {
            "employee_id": self.id,
            "employee_name": self.name,
            "employee_country": self.country,
            "office_country": self.country,
            "office_location": self.office,
            "department": self.department,
            "role": self.job_title,
            "date_of_joining": self.start_date.isoformat(),
        }


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    # Only a hash of the cookie's token is stored, so a copy of the database can't sign anyone in.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UserStore:
    """Accounts and sign-in sessions, in the same database as the interactions."""

    def __init__(self, database_url: str | None = None) -> None:
        url = database_url or database_url_from_env()
        ensure_sqlite_directory(url)
        self._engine = create_engine(url)
        Base.metadata.create_all(self._engine)
        for table in Base.metadata.sorted_tables:
            add_missing_columns(self._engine, table)
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)

    def count(self) -> int:
        with self._sessions() as session:
            return int(session.scalar(select(func.count()).select_from(User)) or 0)

    def create_user(
        self,
        *,
        email: str,
        name: str,
        password: str,
        role: str,
        job_title: str,
        department: str,
        office: str,
        country: str,
        start_date: date,
        manager_name: str | None = None,
        pronouns: str | None = None,
    ) -> User:
        if role not in (ROLE_EMPLOYEE, ROLE_HR):
            raise ValueError(f"Unknown role {role!r}.")
        user = User(
            id=str(uuid.uuid4()),
            email=normalize_email(email),
            name=name,
            password_hash=hash_password(password),
            role=role,
            job_title=job_title,
            department=department,
            office=office,
            country=country,
            manager_name=manager_name,
            start_date=start_date,
            pronouns=pronouns,
            created_at=datetime.now(timezone.utc),
        )
        with self._sessions.begin() as session:
            session.add(user)
        return user

    def get(self, user_id: str | None) -> User | None:
        if not user_id:
            return None
        with self._sessions() as session:
            return session.get(User, user_id)

    def names(self) -> list[str]:
        """Everyone's full name, for masking them in traces sent outside the company."""
        with self._sessions() as session:
            return list(session.scalars(select(User.name)))

    def get_by_email(self, email: str) -> User | None:
        with self._sessions() as session:
            return session.scalar(select(User).where(User.email == normalize_email(email)))

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.get_by_email(email)
        if user is None:
            # Hash anyway, so an unknown email takes as long to reject as a wrong password.
            verify_password(password, _UNKNOWN_USER_HASH)
            return None
        return user if verify_password(password, user.password_hash) else None

    def start_session(self, user_id: str, *, now: datetime | None = None) -> str:
        """Signs the user in. Returns the token for the session cookie."""
        token = secrets.token_urlsafe(32)
        started = now or datetime.now(timezone.utc)
        with self._sessions.begin() as session:
            # Expired sessions are cleared out as new ones start.
            session.execute(delete(AuthSession).where(AuthSession.expires_at < started))
            session.add(
                AuthSession(
                    token_hash=_token_hash(token),
                    user_id=user_id,
                    created_at=started,
                    expires_at=started + SESSION_LIFETIME,
                )
            )
        return token

    def user_for_session(self, token: str, *, now: datetime | None = None) -> User | None:
        with self._sessions() as session:
            auth_session = session.get(AuthSession, _token_hash(token))
            if auth_session is None or as_utc(auth_session.expires_at) <= (now or datetime.now(timezone.utc)):
                return None
            return session.get(User, auth_session.user_id)

    def end_session(self, token: str) -> None:
        with self._sessions.begin() as session:
            session.execute(delete(AuthSession).where(AuthSession.token_hash == _token_hash(token)))


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    return hmac.compare_digest(digest.hex(), expected)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


_UNKNOWN_USER_HASH = hash_password(secrets.token_urlsafe(16))
