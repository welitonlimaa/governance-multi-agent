"""
Cultura Agent — classifica a maturidade organizacional usando RAG.

Pipeline:
  1. Chunking do documento markdown
  2. Embedding via sentence-transformers (local)
  3. Indexação no FAISS vector store
  4. Consultas por aspecto cultural
  5. LLM usado APENAS para narrativa final (opcional)

A classificação determinística (scores, traits, bottlenecks) é
feita com regex/keyword matching — sem LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from logger import get_logger

log = get_logger("cultura_agent")

# Dicionários de indicadores culturais

_BUREAUCRATIC_SIGNALS: list[str] = [
    r"hierárquic",
    r"aprovação.*nível",
    r"e-mail formal",
    r"controle e previsibilidade",
    r"processos rígidos",
    r"cadeia de aprovação",
    r"burocraci",
]
_AGILE_SIGNALS: list[str] = [
    r"ágil",
    r"sprint",
    r"squad",
    r"kanban",
    r"iterativ",
    r"colaborati",
    r"autonom",
    r"descentraliz",
]
_INNOVATION_SIGNALS: list[str] = [
    r"inovação",
    r"experimento",
    r"prototip",
    r"hack",
    r"startups?",
    r"cultura de dados",
    r"data.driven",
]
_COLLABORATION_SIGNALS: list[str] = [
    r"slack",
    r"teams",
    r"ferramenta colaborativa",
    r"real.time",
    r"chat",
    r"integraç",
    r"cross.funcional",
]
_IT_BUSINESS_GAP_SIGNALS: list[str] = [
    r"dificuldade.*resposta.*ti",
    r"lentidão.*ti",
    r"barreira.*ti",
    r"ti.*validar",
    r"aprovação.*ti",
    r"negócio.*ti",
]

# Aspectos avaliados e suas consultas para o RAG
_CULTURE_QUERIES: dict[str, str] = {
    "decision_making": "tomada de decisão aprovação hierárquica",
    "it_business_alignment": "integração TI negócio comunicação",
    "collaboration_tools": "ferramentas colaborativas comunicação tempo real",
    "innovation_culture": "inovação experimentos cultura mudança",
    "agility": "agilidade processos velocidade entrega",
}


@dataclass
class CulturaReport:
    culture_type: str = "Indefinida"
    maturity_score: float = 0.0  # 0-10
    digital_readiness: str = "indefinida"  # baixa | média | alta
    traits: list[str] = field(default_factory=list)
    bottlenecks: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    aspect_scores: dict[str, float] = field(default_factory=dict)
    rag_context: list[str] = field(default_factory=list)  # chunks recuperados
    llm_narrative: str = ""  # preenchido pelo LLM (opcional)

    def to_dict(self) -> dict[str, Any]:
        return {
            "culture_type": self.culture_type,
            "maturity_score": round(self.maturity_score, 1),
            "max_score": 10.0,
            "digital_readiness": self.digital_readiness,
            "traits": self.traits,
            "bottlenecks": self.bottlenecks,
            "strengths": self.strengths,
            "aspect_scores": {k: round(v, 2) for k, v in self.aspect_scores.items()},
            "rag_context_count": len(self.rag_context),
            "llm_narrative": self.llm_narrative,
        }


def _count_signals(text: str, patterns: list[str]) -> int:
    """Conta quantos padrões regex estão presentes no texto."""
    text_lower = text.lower()
    return sum(1 for p in patterns if re.search(p, text_lower))


def _classify_culture(
    bureaucratic: int,
    agile: int,
    innovation: int,
    collaboration: int,
) -> tuple[str, str]:
    """
    Determina tipo cultural e readiness digital.
    Retorna (culture_type, digital_readiness).
    """
    if bureaucratic >= 4 and agile <= 1:
        return "Burocrática / Hierárquica", "baixa"
    if bureaucratic >= 3 and agile >= 2:
        return "Tradicional em Transição", "média-baixa"
    if agile >= 3 and innovation >= 2:
        return "Ágil / Orientada a Dados", "alta"
    if collaboration >= 3:
        return "Colaborativa", "média-alta"
    if innovation >= 3:
        return "Inovadora", "alta"
    return "Conservadora", "média"


def _compute_maturity_score(
    bureaucratic: int,
    agile: int,
    innovation: int,
    collaboration: int,
    it_business_gap: int,
) -> float:
    """
    Score 0-10 de maturidade digital.
    Penaliza burocracia e gaps TI/negócio; recompensa agilidade e inovação.
    """
    base = 5.0
    base += agile * 0.8
    base += innovation * 0.7
    base += collaboration * 0.5
    base -= bureaucratic * 0.6
    base -= it_business_gap * 0.4
    return max(0.0, min(10.0, base))


class CulturaAgent:
    """
    Analisa documentos organizacionais usando RAG + keyword matching.
    A classificação é determinística; LLM só gera narrativa.
    """

    def __init__(
        self,
        cultura_text: str,
        llm_provider=None,
    ) -> None:
        self.cultura_text = cultura_text
        self.llm = llm_provider
        self._vector_store = None
        self._embedder = None

    def _setup_rag(self) -> None:
        """
        Inicializa embedder e vector store, indexa o documento.
        Falha graciosamente: se o modelo não puder ser carregado
        (sem internet, sem GPU, sem espaço), o agente continua
        usando apenas keyword matching — sem interromper o fluxo.
        """
        try:
            from rag.embedder import LocalEmbedder
            from rag.vector_store import FAISSVectorStore, chunk_text

            self._embedder = LocalEmbedder()
            self._vector_store = FAISSVectorStore(dim=self._embedder.dim)

            # Tenta carregar índice existente
            loaded = self._vector_store.load()
            if not loaded:
                chunks = chunk_text(self.cultura_text, chunk_size=80, overlap=15)
                if chunks:
                    embeddings = self._embedder.embed_batch(chunks)
                    meta = [
                        {"chunk_index": i, "source": "cultura"}
                        for i in range(len(chunks))
                    ]
                    self._vector_store.add_documents(chunks, embeddings, meta)
                    self._vector_store.persist()
                    log.info("rag_indexed", chunks=len(chunks))
                else:
                    log.warning("rag_no_chunks")

        except ImportError as exc:
            log.warning("rag_unavailable", reason=str(exc))
        except Exception as exc:
            log.warning(
                "rag_setup_failed",
                reason=str(exc)[:120],
                fallback="keyword-only analysis will be used",
            )
            self._embedder = None
            self._vector_store = None

    def _rag_query(self, query: str, top_k: int = 2) -> list[str]:
        """Consulta o vector store e retorna chunks relevantes."""
        if not self._vector_store or not self._embedder:
            return []
        try:
            q_embedding = self._embedder.embed(query)
            results = self._vector_store.query(q_embedding, top_k=top_k)
            return [r["text"] for r in results if r["score"] > 0.3]
        except Exception as exc:
            log.warning("rag_query_error", error=str(exc))
            return []

    def run(self) -> CulturaReport:
        log.info("cultura_agent_start", text_length=len(self.cultura_text))
        report = CulturaReport()

        if not self.cultura_text.strip():
            log.warning("cultura_empty_document")
            report.culture_type = "Documento não disponível"
            return report

        # RAG
        self._setup_rag()

        # Contagem de sinais (determinística)
        text = self.cultura_text
        b_count = _count_signals(text, _BUREAUCRATIC_SIGNALS)
        a_count = _count_signals(text, _AGILE_SIGNALS)
        i_count = _count_signals(text, _INNOVATION_SIGNALS)
        c_count = _count_signals(text, _COLLABORATION_SIGNALS)
        gap_count = _count_signals(text, _IT_BUSINESS_GAP_SIGNALS)

        log.debug(
            "cultura_signals",
            bureaucratic=b_count,
            agile=a_count,
            innovation=i_count,
            collaboration=c_count,
            gap=gap_count,
        )

        # recuperar contexto por aspecto
        all_context: list[str] = []
        aspect_scores: dict[str, float] = {}

        for aspect, query in _CULTURE_QUERIES.items():
            chunks = self._rag_query(query, top_k=2)
            all_context.extend(chunks)
            # Score simples: presença de chunks relevantes + sinais
            aspect_scores[aspect] = min(1.0, len(chunks) * 0.4 + 0.2)

        report.rag_context = list(dict.fromkeys(all_context))  # dedup preservando ordem
        report.aspect_scores = aspect_scores

        # Classificação cultural
        report.culture_type, report.digital_readiness = _classify_culture(
            b_count, a_count, i_count, c_count
        )

        # Score de maturidade
        report.maturity_score = _compute_maturity_score(
            b_count, a_count, i_count, c_count, gap_count
        )

        # Traits, bottlenecks e strengths (baseados em sinais)
        if b_count >= 2:
            report.traits.append("Tomada de decisão centralizada e hierárquica")
        if gap_count >= 1:
            report.traits.append("Gap perceptível entre TI e áreas de negócio")
        if c_count == 0:
            report.traits.append("Ausência de ferramentas colaborativas estruturadas")
        if i_count == 0:
            report.traits.append("Baixa orientação a inovação e experimentação")
        if a_count >= 2:
            report.traits.append("Práticas ágeis presentes na organização")

        if b_count >= 2:
            report.bottlenecks.append(
                "Aprovações em múltiplos níveis hierárquicos retardam entrega"
            )
        if gap_count >= 1:
            report.bottlenecks.append(
                "TI como gargalo para adoção de novas ferramentas"
            )
        if c_count == 0:
            report.bottlenecks.append(
                "Comunicação assíncrona (e-mail) limita velocidade de resposta"
            )

        if a_count >= 1:
            report.strengths.append("Abertura incipiente a metodologias ágeis")
        if i_count >= 1:
            report.strengths.append("Consciência sobre necessidade de mudança cultural")

        # LLM recebe o report já calculado e gera apenas linguagem natural.
        if self.llm:
            try:
                report.llm_narrative = self.llm.summarize("cultura", report.to_dict())
            except Exception as exc:
                log.warning("cultura_llm_error", error=str(exc))
                report.llm_narrative = f"[LLM indisponível: {exc}]"

        log.info(
            "cultura_agent_complete",
            culture_type=report.culture_type,
            maturity_score=round(report.maturity_score, 1),
            digital_readiness=report.digital_readiness,
        )
        return report
