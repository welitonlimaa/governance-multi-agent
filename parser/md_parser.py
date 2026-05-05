"""
parser/md_parser.py
Extrai dados do arquivo .md
"""

from pathlib import Path
from typing import Any

from logger import get_logger

log = get_logger("md_parser")


def parse(filepath: str | Path) -> str:
    """
    Ponto de entrada principal.
    Lê o arquivo .md e retorna o texto da seção de cultura organizacional.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    log.info("parsing_file", path=str(path))
    content = path.read_text(encoding="utf-8")

    log.info("parse_ok", result=len(content))

    return content
