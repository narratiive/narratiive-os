from __future__ import annotations

import json
import os
import fcntl
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


class ModelBudgetConfigurationError(RuntimeError):
    pass


class ModelBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    cache_read_usd_per_mtok: Decimal
    cache_write_usd_per_mtok: Decimal

    def cost(self, usage: TokenUsage) -> Decimal:
        million = Decimal(1_000_000)
        return (
            Decimal(usage.input_tokens) * self.input_usd_per_mtok
            + Decimal(usage.output_tokens) * self.output_usd_per_mtok
            + Decimal(usage.cache_read_tokens) * self.cache_read_usd_per_mtok
            + Decimal(usage.cache_write_tokens) * self.cache_write_usd_per_mtok
        ) / million


@dataclass(frozen=True, slots=True)
class ModelBudgetSnapshot:
    period: str
    usage: TokenUsage
    estimated_cost_usd: Decimal
    warning_limit_usd: Decimal
    hard_limit_usd: Decimal
    reserved_cost_usd: Decimal = Decimal("0")

    @property
    def warning_reached(self) -> bool:
        return self.estimated_cost_usd >= self.warning_limit_usd

    @property
    def hard_limit_reached(self) -> bool:
        return self.estimated_cost_usd + self.reserved_cost_usd >= self.hard_limit_usd


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    reservation_id: str
    amount_usd: Decimal
    expires_at: datetime


class HostedModelBudgetGuard:
    """Read-only OpenClaw accounting plus a small append-only direct-API ledger.

    The guard deliberately reads token metadata only. It never reads or emits prompt,
    response, tool, or credential content from OpenClaw transcripts.
    """

    def __init__(
        self,
        *,
        openclaw_state_dir: Path,
        direct_usage_ledger: Path,
        warning_limit_usd: Decimal,
        hard_limit_usd: Decimal,
        pricing: ModelPricing,
        default_request_reserve_usd: Decimal = Decimal("1"),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if warning_limit_usd <= 0 or hard_limit_usd <= 0:
            raise ModelBudgetConfigurationError("model spending limits must be positive")
        if warning_limit_usd >= hard_limit_usd:
            raise ModelBudgetConfigurationError("model warning limit must be below the hard limit")
        if default_request_reserve_usd < 0:
            raise ModelBudgetConfigurationError("model request reserve cannot be negative")
        self.openclaw_state_dir = openclaw_state_dir
        self.direct_usage_ledger = direct_usage_ledger
        self.warning_limit_usd = warning_limit_usd
        self.hard_limit_usd = hard_limit_usd
        self.pricing = pricing
        self.default_request_reserve_usd = default_request_reserve_usd
        self.reservation_state = direct_usage_ledger.with_name("reservations.json")
        self.lock_path = direct_usage_ledger.with_name("budget.lock")
        self._now = now

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        repository_root: Path | None = None,
    ) -> "HostedModelBudgetGuard | None":
        active = os.environ if env is None else env
        hard_raw = str(active.get("TONY_HOSTED_MODEL_MONTHLY_LIMIT_USD") or "").strip()
        warning_raw = str(active.get("TONY_HOSTED_MODEL_WARNING_USD") or "").strip()
        if not hard_raw and not warning_raw:
            return None
        if not hard_raw or not warning_raw:
            raise ModelBudgetConfigurationError(
                "both TONY_HOSTED_MODEL_MONTHLY_LIMIT_USD and TONY_HOSTED_MODEL_WARNING_USD are required"
            )
        root = repository_root or Path(__file__).resolve().parents[1]
        state_dir = Path(
            str(active.get("OPENCLAW_STATE_DIR") or Path.home() / ".openclaw")
        ).expanduser()
        ledger = Path(
            str(
                active.get("TONY_HOSTED_MODEL_USAGE_LEDGER")
                or root / ".runtime" / "model-usage" / "direct-api.jsonl"
            )
        ).expanduser()
        return cls(
            openclaw_state_dir=state_dir,
            direct_usage_ledger=ledger,
            warning_limit_usd=_decimal(warning_raw, "warning limit"),
            hard_limit_usd=_decimal(hard_raw, "hard limit"),
            default_request_reserve_usd=_decimal(
                str(active.get("TONY_HOSTED_MODEL_REQUEST_RESERVE_USD") or "1"),
                "request reserve",
            ),
            pricing=ModelPricing(
                input_usd_per_mtok=_decimal(
                    str(active.get("TONY_HOSTED_MODEL_INPUT_USD_PER_MTOK") or "3"), "input price"
                ),
                output_usd_per_mtok=_decimal(
                    str(active.get("TONY_HOSTED_MODEL_OUTPUT_USD_PER_MTOK") or "15"), "output price"
                ),
                cache_read_usd_per_mtok=_decimal(
                    str(active.get("TONY_HOSTED_MODEL_CACHE_READ_USD_PER_MTOK") or "0.30"), "cache-read price"
                ),
                # Conservative default: Anthropic's one-hour cache-write rate.
                cache_write_usd_per_mtok=_decimal(
                    str(active.get("TONY_HOSTED_MODEL_CACHE_WRITE_USD_PER_MTOK") or "6"), "cache-write price"
                ),
            ),
        )

    def snapshot(self) -> ModelBudgetSnapshot:
        now = self._now().astimezone(timezone.utc)
        period = now.strftime("%Y-%m")
        with self._lock():
            usage = self._openclaw_usage(period) + self._direct_usage(period)
            reservations = self._active_reservations(now, persist_pruned=True)
        return ModelBudgetSnapshot(
            period=period,
            usage=usage,
            estimated_cost_usd=self.pricing.cost(usage),
            warning_limit_usd=self.warning_limit_usd,
            hard_limit_usd=self.hard_limit_usd,
            reserved_cost_usd=sum((item.amount_usd for item in reservations), Decimal("0")),
        )

    def require_capacity(self, *, reserve_usd: Decimal = Decimal("0")) -> ModelBudgetSnapshot:
        if reserve_usd < 0:
            raise ValueError("model budget reserve cannot be negative")
        snapshot = self.snapshot()
        if snapshot.estimated_cost_usd + snapshot.reserved_cost_usd + reserve_usd >= snapshot.hard_limit_usd:
            raise ModelBudgetExceeded(
                "Tony's hosted-model monthly spending limit has been reached; "
                "consequential reasoning will not silently fall back to a weaker model"
            )
        return snapshot

    def reserve_capacity(
        self,
        *,
        reserve_usd: Decimal | None = None,
        ttl_seconds: int = 3600,
    ) -> BudgetReservation:
        amount = self.default_request_reserve_usd if reserve_usd is None else reserve_usd
        if amount < 0:
            raise ValueError("model budget reserve cannot be negative")
        if ttl_seconds <= 0:
            raise ValueError("model budget reservation TTL must be positive")
        now = self._now().astimezone(timezone.utc)
        period = now.strftime("%Y-%m")
        with self._lock():
            usage = self._openclaw_usage(period) + self._direct_usage(period)
            reservations = self._active_reservations(now, persist_pruned=False)
            committed = self.pricing.cost(usage)
            pending = sum((item.amount_usd for item in reservations), Decimal("0"))
            if committed + pending + amount >= self.hard_limit_usd:
                raise ModelBudgetExceeded(
                    "Tony's hosted-model monthly spending limit has been reached; "
                    "consequential reasoning will not silently fall back to a weaker model"
                )
            reservation = BudgetReservation(
                reservation_id=uuid.uuid4().hex,
                amount_usd=amount,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._write_reservations((*reservations, reservation))
            return reservation

    def release_reservation(self, reservation: BudgetReservation) -> None:
        with self._lock():
            active = self._active_reservations(self._now().astimezone(timezone.utc), persist_pruned=False)
            self._write_reservations(
                tuple(item for item in active if item.reservation_id != reservation.reservation_id)
            )

    def record_direct_usage(
        self,
        *,
        provider: str,
        model: str,
        response_id: str,
        usage: TokenUsage,
    ) -> None:
        record = {
            "recorded_at": self._now().astimezone(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "response_id": response_id,
            "usage": {
                "input": usage.input_tokens,
                "output": usage.output_tokens,
                "cacheRead": usage.cache_read_tokens,
                "cacheWrite": usage.cache_write_tokens,
            },
        }
        with self._lock():
            self._append_direct_record(record)

    def settle_direct_usage(
        self,
        reservation: BudgetReservation,
        *,
        provider: str,
        model: str,
        response_id: str,
        usage: TokenUsage,
    ) -> None:
        record = self._direct_record(provider, model, response_id, usage)
        with self._lock():
            self._append_direct_record(record)
            active = self._active_reservations(self._now().astimezone(timezone.utc), persist_pruned=False)
            self._write_reservations(
                tuple(item for item in active if item.reservation_id != reservation.reservation_id)
            )

    def _direct_record(
        self, provider: str, model: str, response_id: str, usage: TokenUsage
    ) -> dict[str, Any]:
        return {
            "recorded_at": self._now().astimezone(timezone.utc).isoformat(),
            "provider": provider,
            "model": model,
            "response_id": response_id,
            "usage": {
                "input": usage.input_tokens,
                "output": usage.output_tokens,
                "cacheRead": usage.cache_read_tokens,
                "cacheWrite": usage.cache_write_tokens,
            },
        }

    def _append_direct_record(self, record: Mapping[str, Any]) -> None:
        self.direct_usage_ledger.parent.mkdir(parents=True, exist_ok=True)
        with self.direct_usage_ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.direct_usage_ledger.chmod(0o600)

    def _openclaw_usage(self, period: str) -> TokenUsage:
        records: list[tuple[str, TokenUsage]] = []
        for path in self.openclaw_state_dir.glob("agents/*/sessions/*.jsonl*"):
            if ".trajectory.jsonl" in path.name or path.name.endswith(".lock"):
                continue
            records.extend(_usage_records(path, period, openclaw=True))
        return _deduplicated_usage(records)

    def _direct_usage(self, period: str) -> TokenUsage:
        return _deduplicated_usage(_usage_records(self.direct_usage_ledger, period, openclaw=False))

    @contextmanager
    def _lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            self.lock_path.chmod(0o600)
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _active_reservations(
        self, now: datetime, *, persist_pruned: bool
    ) -> tuple[BudgetReservation, ...]:
        try:
            payload = json.loads(self.reservation_state.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ()
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelBudgetConfigurationError("model budget reservation state is unreadable") from exc
        values = payload.get("reservations") if isinstance(payload, Mapping) else None
        if not isinstance(values, list):
            raise ModelBudgetConfigurationError("model budget reservation state is invalid")
        active: list[BudgetReservation] = []
        for value in values:
            if not isinstance(value, Mapping):
                raise ModelBudgetConfigurationError("model budget reservation is invalid")
            try:
                expires_at = datetime.fromisoformat(str(value.get("expires_at") or "").replace("Z", "+00:00"))
            except ValueError as exc:
                raise ModelBudgetConfigurationError("model budget reservation expiry is invalid") from exc
            if expires_at.tzinfo is None:
                raise ModelBudgetConfigurationError("model budget reservation expiry must be timezone-aware")
            reservation = BudgetReservation(
                reservation_id=str(value.get("reservation_id") or ""),
                amount_usd=_decimal(str(value.get("amount_usd") or ""), "reservation amount"),
                expires_at=expires_at.astimezone(timezone.utc),
            )
            if not reservation.reservation_id:
                raise ModelBudgetConfigurationError("model budget reservation id is required")
            if reservation.expires_at > now:
                active.append(reservation)
        result = tuple(active)
        if persist_pruned and len(result) != len(values):
            self._write_reservations(result)
        return result

    def _write_reservations(self, reservations: Iterable[BudgetReservation]) -> None:
        target = self.reservation_state
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "reservations": [
                {
                    "reservation_id": item.reservation_id,
                    "amount_usd": str(item.amount_usd),
                    "expires_at": item.expires_at.astimezone(timezone.utc).isoformat(),
                }
                for item in reservations
            ]
        }
        descriptor, temporary_name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(0o600)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()


def token_usage_from_anthropic(payload: Mapping[str, Any]) -> TokenUsage:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return TokenUsage()
    return TokenUsage(
        input_tokens=_non_negative_int(usage.get("input_tokens")),
        output_tokens=_non_negative_int(usage.get("output_tokens")),
        cache_read_tokens=_non_negative_int(usage.get("cache_read_input_tokens")),
        cache_write_tokens=_non_negative_int(usage.get("cache_creation_input_tokens")),
    )


def _usage_records(path: Path, period: str, *, openclaw: bool) -> Iterable[tuple[str, TokenUsage]]:
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    records: list[tuple[str, TokenUsage]] = []
    with handle:
        for line in handle:
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(event, Mapping):
                continue
            timestamp = str(event.get("timestamp") if openclaw else event.get("recorded_at") or "")
            if not timestamp.startswith(period + "-"):
                continue
            message = event.get("message") if openclaw else event
            if not isinstance(message, Mapping):
                continue
            provider = str(message.get("provider") or event.get("provider") or "").casefold()
            if provider != "anthropic":
                continue
            usage = message.get("usage")
            if not isinstance(usage, Mapping):
                continue
            response_id = str(message.get("responseId") or message.get("response_id") or event.get("id") or "")
            if not response_id:
                continue
            records.append(
                (
                    response_id,
                    TokenUsage(
                        input_tokens=_non_negative_int(usage.get("input")),
                        output_tokens=_non_negative_int(usage.get("output")),
                        cache_read_tokens=_non_negative_int(usage.get("cacheRead")),
                        cache_write_tokens=_non_negative_int(usage.get("cacheWrite")),
                    ),
                )
            )
    return records


def _deduplicated_usage(records: Iterable[tuple[str, TokenUsage]]) -> TokenUsage:
    total = TokenUsage()
    seen: set[str] = set()
    for response_id, usage in records:
        if response_id in seen:
            continue
        seen.add(response_id)
        total += usage
    return total


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ModelBudgetConfigurationError(f"{label} must be a decimal number") from exc
    if parsed < 0:
        raise ModelBudgetConfigurationError(f"{label} cannot be negative")
    return parsed
