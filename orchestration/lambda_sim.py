"""
Simula o runtime do AWS Lambda localmente.
Cada agente é uma LambdaHandler isolada com retry e simulação de falha.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any, Callable

from config import FAILURE_RATE
from logger import get_logger
from mcp.context import MCPContext, MCPResponse

log = get_logger("lambda_sim")

LambdaHandler = Callable[[MCPContext], MCPResponse]


class LambdaRuntime:
    """
    Executa um LambdaHandler com:
      - timeout simulado
      - injeção de falha configurável (FAILURE_RATE)
      - retry com backoff exponencial
      - métricas básicas (duração, status)
    """

    def __init__(
        self,
        handler: LambdaHandler,
        function_name: str,
        max_retries: int = 2,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.handler = handler
        self.function_name = function_name
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

    async def invoke(self, ctx: MCPContext) -> MCPResponse:
        """Invoca o handler com retry e simulação de falha."""
        attempt = 0
        last_error: str = ""

        while attempt <= self.max_retries:
            start = time.perf_counter()
            try:
                # Simula falha aleatória de provider
                if FAILURE_RATE > 0 and random.random() < FAILURE_RATE:
                    raise RuntimeError(
                        f"[SIMULATED] Rate limit exceeded on {self.function_name}"
                    )

                log.debug(
                    "lambda_invoke",
                    function=self.function_name,
                    attempt=attempt + 1,
                    execution_id=ctx.execution_id,
                )

                # Executa handler (pode ser sync ou async)
                if asyncio.iscoroutinefunction(self.handler):
                    response = await asyncio.wait_for(
                        self.handler(ctx), timeout=self.timeout_seconds
                    )
                else:
                    response = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, self.handler, ctx
                        ),
                        timeout=self.timeout_seconds,
                    )

                duration_ms = (time.perf_counter() - start) * 1000
                log.info(
                    "lambda_success",
                    function=self.function_name,
                    duration_ms=round(duration_ms, 2),
                    execution_id=ctx.execution_id,
                )
                return response

            except asyncio.TimeoutError:
                last_error = f"Timeout after {self.timeout_seconds}s"
                log.warning(
                    "lambda_timeout",
                    function=self.function_name,
                    attempt=attempt + 1,
                )
            except Exception as exc:
                last_error = str(exc)
                log.warning(
                    "lambda_error",
                    function=self.function_name,
                    attempt=attempt + 1,
                    error=last_error,
                )

            attempt += 1
            if attempt <= self.max_retries:
                backoff = 2**attempt * 0.1  # 0.2s, 0.4s, ...
                log.info("lambda_retry", backoff_seconds=backoff)
                await asyncio.sleep(backoff)

        log.error(
            "lambda_failed",
            function=self.function_name,
            attempts=self.max_retries + 1,
            error=last_error,
        )
        return MCPResponse(
            agent=self.function_name,
            status="error",
            error=last_error,
            execution_id=ctx.execution_id,
        )
