"""OpenFeature **server** provider for Shipeasy.

Lets apps standardised on the CNCF OpenFeature API plug Shipeasy in as the
backing provider::

    from openfeature import api
    from shipeasy import Engine
    from shipeasy.openfeature import ShipeasyProvider

    engine = Engine(api_key="sdk_server_...")
    engine.init()
    api.set_provider(ShipeasyProvider(engine))

    of = api.get_client()
    on = of.get_boolean_value("new_checkout", False, EvaluationContext("u1"))

Pure adapter over :class:`shipeasy.Engine` — no change to evaluation. The
``openfeature-sdk`` package is an OPTIONAL dependency; install the extra::

    pip install shipeasy[openfeature]

Importing the base ``shipeasy`` package never requires ``openfeature-sdk``;
only importing ``shipeasy.openfeature`` (this module) does.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence, Union

try:
    from openfeature.evaluation_context import EvaluationContext
    from openfeature.exception import ErrorCode
    from openfeature.flag_evaluation import FlagResolutionDetails, Reason
    from openfeature.provider import AbstractProvider
    from openfeature.provider.metadata import Metadata
except ModuleNotFoundError as exc:  # pragma: no cover - exercised without the extra
    raise ModuleNotFoundError(
        "shipeasy.openfeature requires the 'openfeature-sdk' package. "
        "Install it with: pip install shipeasy[openfeature]"
    ) from exc

from ._client import Engine
from ._detail import (
    CLIENT_NOT_READY,
    DEFAULT,
    FLAG_NOT_FOUND,
    OFF,
    OVERRIDE,
    RULE_MATCH,
)

# Shipeasy FlagReason → (OpenFeature reason, optional ErrorCode). Per doc 20:
#   RULE_MATCH       → TARGETING_MATCH
#   DEFAULT          → DEFAULT
#   OFF              → DISABLED
#   OVERRIDE         → STATIC
#   FLAG_NOT_FOUND   → ERROR (error_code FLAG_NOT_FOUND)
#   CLIENT_NOT_READY → ERROR (error_code PROVIDER_NOT_READY)
_REASON_MAP: dict[str, tuple[str, Optional[ErrorCode]]] = {
    RULE_MATCH: (Reason.TARGETING_MATCH, None),
    DEFAULT: (Reason.DEFAULT, None),
    OFF: (Reason.DISABLED, None),
    OVERRIDE: (Reason.STATIC, None),
    FLAG_NOT_FOUND: (Reason.ERROR, ErrorCode.FLAG_NOT_FOUND),
    CLIENT_NOT_READY: (Reason.ERROR, ErrorCode.PROVIDER_NOT_READY),
}


def _to_user(ctx: Optional[EvaluationContext]) -> dict:
    """Convert an OpenFeature evaluation context into a Shipeasy user dict.

    ``targeting_key`` becomes ``user_id``; every attribute is carried through
    verbatim for targeting. A ``user_id``/``anonymous_id`` already present in
    the attributes is preserved when no ``targeting_key`` is given.
    """
    if ctx is None:
        return {}
    user: dict = dict(ctx.attributes or {})
    if ctx.targeting_key:
        user["user_id"] = ctx.targeting_key
    return user


class ShipeasyProvider(AbstractProvider):
    """Shipeasy OpenFeature provider (server paradigm).

    Wraps a :class:`shipeasy.Engine`; evaluation is local against the cached
    blob, so resolution is effectively synchronous.
    """

    def __init__(self, client: Engine) -> None:
        self._client = client

    def get_metadata(self) -> Metadata:
        return Metadata(name="shipeasy")

    def get_provider_hooks(self) -> list:
        return []

    def initialize(self, evaluation_context: EvaluationContext) -> None:
        self._client.init_once()

    def shutdown(self) -> None:
        self._client.destroy()

    # -- boolean: evaluate the gate ------------------------------------------

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[bool]:
        try:
            detail = self._client.get_flag_detail(flag_key, _to_user(evaluation_context))
        except Exception as exc:  # noqa: BLE001 -- never propagate to OpenFeature
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                error_code=ErrorCode.GENERAL,
                error_message=str(exc),
            )
        reason, error_code = _REASON_MAP.get(detail.reason, (Reason.UNKNOWN, None))
        if error_code is not None:
            return FlagResolutionDetails(
                value=default_value,
                reason=reason,
                error_code=error_code,
            )
        return FlagResolutionDetails(value=detail.value, reason=reason)

    # -- string / int / float / object: route to get_config ------------------

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[str]:
        return self._resolve_config(flag_key, default_value, str)

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[int]:
        return self._resolve_config(flag_key, default_value, int)

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[float]:
        return self._resolve_config(flag_key, default_value, float)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Union[Sequence, Mapping],
        evaluation_context: Optional[EvaluationContext] = None,
    ) -> FlagResolutionDetails[Union[Sequence, Mapping]]:
        return self._resolve_config(flag_key, default_value, (dict, list))

    _SENTINEL = object()

    def _resolve_config(
        self,
        flag_key: str,
        default_value: Any,
        expected_type: Any,
    ) -> FlagResolutionDetails:
        try:
            value = self._client.get_config(flag_key, default=self._SENTINEL)
        except Exception as exc:  # noqa: BLE001
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                error_code=ErrorCode.GENERAL,
                error_message=str(exc),
            )
        # Absent → default with reason DEFAULT.
        if value is self._SENTINEL:
            return FlagResolutionDetails(value=default_value, reason=Reason.DEFAULT)
        # Present but wrong type → TYPE_MISMATCH (return the default).
        # ``bool`` is a subclass of ``int`` in Python; never accept a bool where
        # an int/float is requested.
        type_ok = isinstance(value, expected_type)
        if expected_type in (int, float) and isinstance(value, bool):
            type_ok = False
        if not type_ok:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                error_code=ErrorCode.TYPE_MISMATCH,
                error_message=(
                    f"config value {value!r} is not of type "
                    f"{getattr(expected_type, '__name__', expected_type)}"
                ),
            )
        return FlagResolutionDetails(value=value, reason=Reason.TARGETING_MATCH)


__all__ = ["ShipeasyProvider"]
