"""Kullanıcı hesapları (#278): argon2id karması, doğrulama, kilitlenme, parolanın sızmaması.

Veritabanı gerekmez: karar mantığı (`evaluate_login`) düz nesneler üzerinde, `verify_credentials`
sahte oturumla denenir. Gerçek DB testleri `test_accounts_integration.py` içindedir.
"""

import csv
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from structlog.testing import capture_logs

from app.db.models.accounts import UserAccount
from app.domain.accounts import (
    LOCK_MINUTES,
    MAX_FAILED_ATTEMPTS,
    MIN_PASSWORD_LENGTH,
    AccountRole,
)
from app.services import accounts
from app.services.accounts import (
    LoginFailure,
    PasswordPolicyError,
    derive_username,
    evaluate_login,
    generate_password,
    hash_password,
    verify_credentials,
)
from scripts.seed_accounts import _append_credentials

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
GOOD = secrets.token_urlsafe(16)  # çalışma zamanında üretilir; sabit parola yok
WRONG = secrets.token_urlsafe(16)
ROOT = Path(__file__).resolve().parents[2]


def make_account(**overrides: Any) -> UserAccount:
    data: dict[str, Any] = {
        "id": uuid4(),
        "username": "ahmet.yilmaz",
        "password_hash": hash_password(GOOD),
        "role": "owner",
        "customer_id": uuid4(),
        "is_active": True,
        "failed_attempts": 0,
        "locked_until": None,
    }
    data.update(overrides)
    return UserAccount(**data)


# --- Karma ve politika ---------------------------------------------------------------------


def test_hash_is_argon2id_and_not_plaintext() -> None:
    hashed = hash_password(GOOD)
    assert hashed.startswith("$argon2id$")
    assert GOOD not in hashed
    assert hash_password(GOOD) != hashed  # her karmada farklı tuz


def test_password_policy_requires_min_length() -> None:
    with pytest.raises(PasswordPolicyError):
        hash_password("a" * (MIN_PASSWORD_LENGTH - 1))
    assert hash_password("a" * MIN_PASSWORD_LENGTH)


def test_generated_passwords_are_random_and_meet_policy() -> None:
    passwords = {generate_password() for _ in range(50)}
    assert len(passwords) == 50
    assert all(len(p) >= MIN_PASSWORD_LENGTH for p in passwords)


# --- Doğrulama -----------------------------------------------------------------------------


def test_correct_password_succeeds_and_returns_role() -> None:
    account = make_account()
    result = evaluate_login(account, GOOD, NOW)
    assert result.ok and result.role is AccountRole.OWNER
    assert result.customer_id == account.customer_id and result.failure is None


def test_wrong_password_fails_and_counts() -> None:
    account = make_account()
    result = evaluate_login(account, WRONG, NOW)
    assert not result.ok and result.failure is LoginFailure.WRONG_PASSWORD
    assert account.failed_attempts == 1 and account.locked_until is None


def test_success_resets_failed_attempts() -> None:
    account = make_account(failed_attempts=3)
    assert evaluate_login(account, GOOD, NOW).ok
    assert account.failed_attempts == 0


def test_account_locks_after_max_failed_attempts() -> None:
    account = make_account()
    results = [evaluate_login(account, WRONG, NOW) for _ in range(MAX_FAILED_ATTEMPTS)]
    assert [r.just_locked for r in results] == [False] * (MAX_FAILED_ATTEMPTS - 1) + [True]
    assert account.locked_until == NOW + timedelta(minutes=LOCK_MINUTES)


def test_locked_account_rejects_even_correct_password_and_keeps_counter() -> None:
    account = make_account(
        failed_attempts=MAX_FAILED_ATTEMPTS, locked_until=NOW + timedelta(minutes=5)
    )
    result = evaluate_login(account, GOOD, NOW)
    assert not result.ok and result.failure is LoginFailure.LOCKED
    assert account.failed_attempts == MAX_FAILED_ATTEMPTS


def test_lock_expires_and_counter_restarts() -> None:
    account = make_account(
        failed_attempts=MAX_FAILED_ATTEMPTS, locked_until=NOW - timedelta(seconds=1)
    )
    assert evaluate_login(account, GOOD, NOW).ok
    assert account.locked_until is None and account.failed_attempts == 0
    # Kilit bittikten sonra ilk yanlış deneme hemen yeniden kilitlemez.
    expired = make_account(
        failed_attempts=MAX_FAILED_ATTEMPTS, locked_until=NOW - timedelta(seconds=1)
    )
    evaluate_login(expired, WRONG, NOW)
    assert expired.failed_attempts == 1 and expired.locked_until is None


def test_inactive_account_cannot_sign_in() -> None:
    result = evaluate_login(make_account(is_active=False), GOOD, NOW)
    assert not result.ok and result.failure is LoginFailure.INACTIVE


def test_unknown_user_fails() -> None:
    result = evaluate_login(None, GOOD, NOW)
    assert not result.ok and result.failure is LoginFailure.UNKNOWN_USER


def test_every_failure_path_still_runs_one_hash_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sabit zamanlılık: kullanıcı yok / kilitli / pasif de bir argon2id doğrulaması yapar."""
    calls: list[str] = []
    real = accounts._verify_hash

    def counting(stored: str, password: str) -> bool:
        calls.append(stored[:10])
        return real(stored, password)

    monkeypatch.setattr(accounts, "_verify_hash", counting)
    cases = [
        None,
        make_account(locked_until=NOW + timedelta(minutes=1)),
        make_account(is_active=False),
        make_account(),
    ]
    for account in cases:
        calls.clear()
        evaluate_login(account, WRONG, NOW)
        assert calls == ["$argon2id$"]


def test_stale_hash_parameters_are_upgraded_on_success() -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)  # eski/zayıf parametreler
    account = make_account(password_hash=weak.hash(GOOD))
    old = account.password_hash
    assert evaluate_login(account, GOOD, NOW).ok
    assert account.password_hash != old and account.password_hash.startswith("$argon2id$")
    assert account.password_changed_at == NOW


# --- verify_credentials (sahte oturum) ---------------------------------------------------------


class _FakeSession:
    def __init__(self, account: UserAccount | None) -> None:
        self.account = account
        self.flushed = 0
        self.statements: list[str] = []

    async def scalar(self, stmt: object) -> UserAccount | None:
        self.statements.append(str(stmt))
        return self.account

    async def flush(self) -> None:
        self.flushed += 1


async def test_verify_credentials_normalizes_username_and_flushes() -> None:
    session = _FakeSession(make_account())
    fake: Any = session
    result = await verify_credentials(fake, "  Ahmet.Yilmaz ", GOOD, now=NOW)
    assert result.ok and session.flushed == 1
    assert "FOR UPDATE" in session.statements[0]  # eşzamanlı denemeler sayacı atlamasın


async def test_failed_login_logs_account_id_but_never_the_password() -> None:
    account = make_account()
    secret = secrets.token_urlsafe(16)
    fake: Any = _FakeSession(account)
    with capture_logs() as logs:
        for _ in range(MAX_FAILED_ATTEMPTS):
            await verify_credentials(fake, "ahmet.yilmaz", secret, now=NOW)
    assert logs  # olaylar yazıldı
    dump = repr(logs)
    assert secret not in dump and GOOD not in dump and account.password_hash not in dump
    assert str(account.id) in dump
    assert any(entry["event"] == "accounts.locked" for entry in logs)


# --- Kullanıcı adı türetme ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ahmet Yılmaz", "ahmet.yilmaz"),
        ("Şükrü Çağlar Öztürk", "sukru.caglar.ozturk"),
        ("  İpek   Üstün ", "ipek.ustun"),
        ("???", "kullanici"),
    ],
)
def test_derive_username_transliterates_turkish(name: str, expected: str) -> None:
    assert derive_username(name, set()) == expected


def test_derive_username_adds_number_on_collision() -> None:
    taken: set[str] = set()
    names = [derive_username("Ali Veli", taken) for _ in range(3)]
    assert names == ["ali.veli", "ali.veli2", "ali.veli3"]
    assert derive_username("Ali Veli", {"ali.veli"}) == "ali.veli2"


# --- Düz parolalar yalnızca yerel dosyada --------------------------------------------------------


def test_credentials_file_is_gitignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "backend/.local/" in ignore


def test_credentials_file_gets_header_once_and_appends(tmp_path: Path) -> None:
    path = tmp_path / ".local" / "seed_credentials.csv"
    _append_credentials(path, [("a", "owner", "p1")])
    _append_credentials(path, [("b", "admin", "p2")])
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows == [["username", "role", "password"], ["a", "owner", "p1"], ["b", "admin", "p2"]]


def test_no_tracked_source_contains_seed_password_file_or_literal_secrets() -> None:
    """Depoda seed_credentials.csv yok (yalnızca git dışı yerel dosya)."""
    tracked_csv = [p for p in ROOT.rglob("seed_credentials*.csv") if ".claude" not in p.parts]
    for path in tracked_csv:
        assert ".local" in path.parts, path  # yalnızca git dışı klasörde bulunabilir
