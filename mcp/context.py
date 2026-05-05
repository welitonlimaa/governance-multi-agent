"""
Camada MCP (Model Context Protocol) – padroniza entrada/saída
de todos os agentes com envelope { input, context, memory }.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class MCPContext:
    """Envelope MCP passado para cada agente."""

    input: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)
    execution_id: str = field(default_factory=lambda: str(uuid4()))

    def enrich(self, **kwargs: Any) -> "MCPContext":
        """Retorna novo MCPContext com contexto adicional (imutável)."""
        new_ctx = MCPContext(
            input=self.input.copy(),
            context={**self.context, **kwargs},
            memory=self.memory.copy(),
            execution_id=self.execution_id,
        )
        return new_ctx

    def remember(self, key: str, value: Any) -> "MCPContext":
        """Armazena valor em memory."""
        new_ctx = MCPContext(
            input=self.input.copy(),
            context=self.context.copy(),
            memory={**self.memory, key: value},
            execution_id=self.execution_id,
        )
        return new_ctx

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "context": self.context,
            "memory": self.memory,
            "execution_id": self.execution_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPContext":
        return cls(
            input=data.get("input", {}),
            context=data.get("context", {}),
            memory=data.get("memory", {}),
            execution_id=data.get("execution_id", str(uuid4())),
        )


@dataclass
class MCPResponse:
    """Resposta padronizada de um agente."""

    agent: str
    status: str  # "success" | "error" | "skipped"
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    execution_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "execution_id": self.execution_id,
        }
