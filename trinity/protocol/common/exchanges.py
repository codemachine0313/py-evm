from abc import ABC, abstractmethod
from functools import partial
from typing import (
    Any,
    Callable,
    Generic,
)

from p2p.protocol import (
    BaseRequest,
    TRequestPayload,
)

from .managers import ExchangeManager
from .normalizers import BaseNormalizer
from .types import (
    TMsg,
    TResult,
)
from .validators import BaseValidator


class BaseExchange(ABC, Generic[TRequestPayload, TMsg, TResult]):
    """
    The exchange object handles a few things, in rough order:

     - convert from friendly input arguments to the protocol arguments
     - generate the appropriate BaseRequest object
     - identify the BaseNormalizer that can convert the response payload to the desired result
     - prepare the BaseValidator that can validate the final result against the requested data
     - (if necessary) prepare a response payload validator, which validates data that is *not*
        present in the final result
     - issue the request to the ExchangeManager, with the request, normalizer, and validators
     - await the normalized & validated response, and return it

    TRequestPayload is the data as passed directly to the p2p command
    TMsg is the data as received directly from the p2p command response
    TResult is the response data after normalization
    """

    def __init__(self, manager: ExchangeManager[TRequestPayload, TMsg, TResult]) -> None:
        self._manager = manager

    async def get_result(
            self,
            request: BaseRequest[TRequestPayload],
            normalizer: BaseNormalizer[TMsg, TResult],
            result_validator: BaseValidator[TResult],
            payload_validator: Callable[[TRequestPayload, TMsg], None],
            timeout: int = None) -> TResult:
        """
        This is a light convenience wrapper around the ExchangeManager's get_result() method.

        It makes sure that:
        - the manager service is running
        - the payload validator is primed with the request payload
        """
        if not self._manager.is_running:
            await self._manager.launch_service(request.response_type)

        # bind the outbound request payload to the payload validator
        message_validator = partial(payload_validator, request.command_payload)

        return await self._manager.get_result(
            request,
            normalizer,
            result_validator.validate_result,
            message_validator,
        )

    @abstractmethod
    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        """
        Issue the request to the peer for the desired data
        """
        raise NotImplementedError()
