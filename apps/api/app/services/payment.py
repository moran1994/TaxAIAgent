"""Payment providers: mock (default) and wechat stub via env config."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


@dataclass
class PayResult:
    ok: bool
    channel: str
    message: str
    external_id: str | None = None


class PaymentProvider:
    name = "base"

    def charge(self, *, ticket_id: int, amount_cents: int, fail: bool = False) -> PayResult:
        raise NotImplementedError


class MockPaymentProvider(PaymentProvider):
    name = "mock_wechat"

    def charge(self, *, ticket_id: int, amount_cents: int, fail: bool = False) -> PayResult:
        if fail:
            return PayResult(ok=False, channel=self.name, message="mock payment failed")
        return PayResult(
            ok=True,
            channel=self.name,
            message="ok",
            external_id=f"MOCK-{ticket_id}-{amount_cents}",
        )


class WeChatStubProvider(PaymentProvider):
    """Placeholder for WeChat Pay native API.

    When WECHAT_MCH_ID / WECHAT_API_KEY are set, still returns a deterministic
    sandbox-style success unless PAYMENT_FORCE_FAIL=1 — real API wiring can
    replace `charge` without changing ticket flow.
    """

    name = "wechat_pay"

    def charge(self, *, ticket_id: int, amount_cents: int, fail: bool = False) -> PayResult:
        settings = get_settings()
        if fail or getattr(settings, "payment_force_fail", False):
            return PayResult(ok=False, channel=self.name, message="wechat pay failed")
        if not settings.wechat_mch_id:
            return PayResult(
                ok=False,
                channel=self.name,
                message="WECHAT_MCH_ID not configured; use PAYMENT_PROVIDER=mock",
            )
        # Stub: pretend prepay success
        return PayResult(
            ok=True,
            channel=self.name,
            message="stub_success",
            external_id=f"WXSTUB-{settings.wechat_mch_id}-{ticket_id}",
        )


def get_payment_provider() -> PaymentProvider:
    settings = get_settings()
    provider = (settings.payment_provider or "mock").lower()
    if provider in {"wechat", "wechat_pay", "wechat_stub"}:
        return WeChatStubProvider()
    return MockPaymentProvider()
