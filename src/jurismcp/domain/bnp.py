"""BNP — Banco Nacional de Precedentes (CNJ) qualified-precedent client.

The BNP (https://bnp.pdpj.jus.br/, "Pangea") is the CNJ's official national
registry of QUALIFIED precedents — súmulas, súmulas vinculantes, repercussão
geral themes, repetitive-appeal themes, IRDR/IAC/IRR, PUIL, OJ and abstract
constitutional review (ADI/ADC/ADO/ADPF) — federating 60+ courts (STF, STJ,
TST, STM, TNU, all 27 state courts, TRF01-06, TRT01-24). Unlike the other
sources in this package it returns the FIXED THESIS of each precedent (plus
its live status), not case-law ementas or full texts.

The backing REST API (``https://pangeabnp.pdpj.jus.br/api/v1``) is public and
unauthenticated but UNDOCUMENTED — the contract below was lifted by inspecting
the portal (aug/2026) and is battle-tested by the sibling pipeline_PJE
project, which imported the full 14.5k-precedent corpus through it.

Integration quirks, each handled below:

* **Empty ``orgaos``/``tipos`` arrays → opaque HTTP 400** ("Requisição
  inválida"). Both lists must always be explicit; when the caller doesn't
  restrict them we send every species and every court that has precedents
  (court list fetched from ``GET /parametros`` and cached for the process
  lifetime, with a hardcoded fallback if that endpoint fails).
* **SUM/SV store the enunciado in ``questao``** and leave ``tese`` as a
  placeholder ("não informado"); we promote ``questao`` → thesis for those
  two species only. For theme-like species (RG, RR, IRDR, IAC, PUIL...)
  ``questao`` is the submitted question, distinct from the thesis — both are
  shown when they differ.
* **Placeholder theses** ("não informado", "sem tese", "n/a", "-", ...) are
  rendered as "(ainda não publicada no BNP)" instead of being dropped: in a
  research tool, knowing the precedent exists and its status IS information.
* **``situacao`` is an open vocabulary** (47+ observed values, often null);
  it is displayed verbatim and never interpreted.
* **The portal is an SPA with no per-precedent deep link**; when a result has
  no paradigm-case link, ``full_text_url`` falls back to the portal root
  (``_PORTAL_URL`` is the single place to change if a deep link ever ships).
* The Elasticsearch backend caps ``total`` at 10.000 — irrelevant for paged
  research (we fetch one page of 20 at a time).
"""

import logging
import re
import unicodedata
from html import unescape
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, override

import httpx

from jurismcp.domain.base import BaseLegalPrecedent

if TYPE_CHECKING:
    from patchright.async_api import Page

_LOGGER = logging.getLogger(__name__)

_BASE_URL = "https://pangeabnp.pdpj.jus.br/api/v1"
_PORTAL_URL = "https://bnp.pdpj.jus.br/"
_RESULTS_PER_PAGE = 20
_MAX_RETRIES = 2
_HTTP_TIMEOUT = 30.0
_HTTP_BAD_REQUEST = 400

_HEADERS = {
    # Browser-like UA — house pattern for the HTTP sources (WAF-friendly).
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Content-Type": "application/json",
}

# The 16 precedent species (stable procedural taxonomy — hardcoded).
_ESPECIES: Final[tuple[str, ...]] = (
    "SUM", "SV", "RG", "RR", "IRR", "IRDR", "IAC", "OJ",
    "PUIL", "SIRDR", "ADI", "ADC", "ADO", "ADPF", "CT", "NT",
)

# Species where the BNP stores the enunciado in `questao` (see module doc).
_ESPECIES_ENUNCIADO_NA_QUESTAO = ("SUM", "SV")

# Placeholder literals the BNP writes when it has no thesis text.
_TESES_PLACEBO: Final[frozenset[str]] = frozenset({
    "nao informado", "nao informada", "nao informado.",
    "sem tese", "sem tese firmada", "n/a", "na", "-", "--",
})

_SEM_TESE = "(ainda não publicada no BNP)"

# Court list fallback, used only when GET /parametros fails. Matches the
# courts observed with precedents in aug/2026 (note: the BNP uses TJDF, not
# TJDFT). Successful /parametros responses replace this via _ORGAOS_CACHE.
_ORGAOS_FALLBACK: Final[tuple[str, ...]] = (
    "STF", "STJ", "TST", "STM", "TNU",
    *(f"TRF0{i}" for i in range(1, 7)),
    *(f"TRT{i:02d}" for i in range(1, 25)),
    "TJAC", "TJAL", "TJAM", "TJAP", "TJBA", "TJCE", "TJDF", "TJES", "TJGO",
    "TJMA", "TJMG", "TJMS", "TJMT", "TJPA", "TJPB", "TJPE", "TJPI", "TJPR",
    "TJRJ", "TJRN", "TJRO", "TJRR", "TJRS", "TJSC", "TJSE", "TJSP", "TJTO",
)

# Process-lifetime cache of the live court list (filled on first success).
_ORGAOS_CACHE: list[str] = []

# Aliases whose BNP sigla differs from the common Brazilian short name.
_TRIBUNAL_ALIASES: Final[dict[str, str]] = {"tjdft": "TJDF"}

_RE_TAG_QUEBRA = re.compile(r"(?i)<\s*(?:br|/p|/div|/li|/tr)\s*/?>")
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_ESPACOS = re.compile(r"[ \t\xa0]+")
_RE_QUEBRAS = re.compile(r"\n{3,}")
_RE_TRF = re.compile(r"^trf\s*0?([1-6])$")
_RE_TRT = re.compile(r"^trt\s*0?(\d{1,2})$")


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _clean_html(value: Any) -> str:
    """Turn the API's HTML thesis/question (literal tags + entities) into clean text."""
    if not value:
        return ""
    text = str(value)
    text = _RE_TAG_QUEBRA.sub("\n", text)
    text = _RE_TAGS.sub("", text)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = _RE_ESPACOS.sub(" ", text)
    text = _RE_QUEBRAS.sub("\n\n", text)
    return text.strip()


def _is_placebo(tese: Any) -> bool:
    """True when the 'thesis' is a filler literal, not an enunciado."""
    if not tese:
        return True
    return _strip_accents(str(tese)).casefold().strip() in _TESES_PLACEBO


def _resolve_enunciado(tipo: str, tese: str, questao: str) -> tuple[str, str | None]:
    """Decide which field carries the precedent's enunciado.

    Returns ``(tese, questao)`` adjusted: placebo theses become ``""``; for
    SUM/SV the real enunciado the BNP stores in ``questao`` is promoted to
    the thesis slot and ``questao`` is cleared (same text twice would just
    duplicate the output).
    """
    tese_limpa = "" if _is_placebo(tese) else str(tese).strip()
    questao_limpa = (questao or "").strip() or None
    if (not tese_limpa
            and questao_limpa
            and (tipo or "").upper() in _ESPECIES_ENUNCIADO_NA_QUESTAO):
        return questao_limpa, None
    return tese_limpa, questao_limpa


def _normalize_tribunal(raw: str) -> str:
    """User-supplied court name → BNP sigla.

    ``trf2`` → ``TRF02``, ``trt1`` → ``TRT01``, ``tjdft`` → ``TJDF``
    (the BNP sigla for the DF court), anything else upper-cased.
    """
    s = (raw or "").strip().lower()
    if s in _TRIBUNAL_ALIASES:
        return _TRIBUNAL_ALIASES[s]
    m = _RE_TRF.match(s)
    if m:
        return f"TRF0{m.group(1)}"
    m = _RE_TRT.match(s)
    if m:
        return f"TRT{int(m.group(1)):02d}"
    return s.upper().replace(" ", "")


async def _all_orgaos() -> list[str]:
    """Every court sigla that has precedents, from ``GET /parametros``.

    Cached for the process lifetime; falls back to ``_ORGAOS_FALLBACK`` with
    a warning when the endpoint fails (a research call must never die because
    the taxonomy endpoint hiccupped).
    """
    if _ORGAOS_CACHE:
        return list(_ORGAOS_CACHE)
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{_BASE_URL}/parametros", headers=_HEADERS
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        _LOGGER.warning(
            "BNP GET /parametros failed (%s); using the hardcoded court list",
            exc,
        )
        return list(_ORGAOS_FALLBACK)
    siglas = [
        o["sigla"]
        for o in data.get("orgaos", [])
        if o.get("sigla") and not o.get("semPrecedentes")
    ]
    if not siglas:
        _LOGGER.warning(
            "BNP GET /parametros returned no courts; using the hardcoded list"
        )
        return list(_ORGAOS_FALLBACK)
    _ORGAOS_CACHE.extend(siglas)
    return list(siglas)


class BnpLegalPrecedent(BaseLegalPrecedent):
    """Model for a qualified precedent returned by the BNP/CNJ API."""

    requires_browser: ClassVar[bool] = False  # direct HTTP POST (JSON REST API)

    @classmethod
    def _parse_results(cls, data: dict[str, Any]) -> list[Self]:
        """Extract precedents from the API's ``{total, resultados}`` payload."""
        items = data.get("resultados") or []
        if not items:
            _LOGGER.info("BNP returned no results")
            return []

        results: list[Self] = []
        for item in items:
            orgao = str(item.get("orgao") or "").strip()
            tipo = str(item.get("tipo") or "").strip().upper()
            nr_raw = item.get("nr")
            try:
                nr = int(nr_raw)  # pyright: ignore[reportArgumentType]
            except (TypeError, ValueError):
                nr = None
            if not item.get("id") or not orgao or not tipo or nr is None:
                _LOGGER.warning("BNP: discarding malformed item: %r", item)
                continue

            tese, questao = _resolve_enunciado(
                tipo,
                _clean_html(item.get("tese")),
                _clean_html(item.get("questao")),
            )
            situacao = str(item.get("situacao") or "").strip()
            atualizacao = str(item.get("ultimaAtualizacao") or "").strip()

            meta_parts = [f"Órgão: {orgao}", f"Espécie: {tipo}", f"Nº: {nr}"]
            meta_parts.append(f"Situação: {situacao or 'não informada'}")
            if atualizacao:
                meta_parts.append(f"Atualização: {atualizacao}")

            body_lines = [f"Tese: {tese or _SEM_TESE}"]
            if questao and questao != tese:
                body_lines.append(f"Questão submetida: {questao}")

            url = next(
                (
                    p.get("link")
                    for p in item.get("processosParadigma") or []
                    if p.get("link")
                ),
                None,
            )

            results.append(
                cls(
                    summary="[" + " | ".join(meta_parts) + "]\n"
                    + "\n".join(body_lines),
                    court=orgao,
                    full_text_url=url or _PORTAL_URL,
                )
            )

        _LOGGER.info(
            "Parsed %d precedent(s) from BNP (total reported: %s)",
            len(results),
            data.get("total"),
        )
        return results

    @override
    @classmethod
    async def research(
        cls,
        browser: "Page",  # interface compatibility; not used (HTTP, no browser)
        *,
        summary_search_prompt: str,
        desired_page: int = 1,
        tribunal: str = "",
        especie: str = "",
        numero: str = "",
        incluir_cancelados: bool = True,
    ) -> list[Self]:
        """Search the BNP via unauthenticated HTTP POST.

        :param tribunal: optional BNP court sigla (``STJ``, ``TJES``,
            ``trf2``...); empty means every court with precedents.
        :param especie: optional species sigla (``SUM``, ``RG``, ``RR``...);
            empty means all 16 species.
        :param numero: optional precedent number for exact lookups.
        :param incluir_cancelados: include cancelled/superseded precedents
            (their status is displayed either way).
        """
        if especie.strip():
            tipo = especie.strip().upper()
            if tipo not in _ESPECIES:
                raise RuntimeError(
                    f"Espécie '{especie}' desconhecida no BNP. Use uma de: "
                    + ", ".join(_ESPECIES)
                )
            tipos = [tipo]
        else:
            tipos = list(_ESPECIES)

        if tribunal.strip():
            sigla = _normalize_tribunal(tribunal)
            if sigla not in _ORGAOS_FALLBACK and sigla not in _ORGAOS_CACHE:
                _LOGGER.warning(
                    "BNP: court sigla %r not in the known list; forwarding "
                    "anyway (the API validates).",
                    sigla,
                )
            orgaos = [sigla]
        else:
            orgaos = await _all_orgaos()

        body = {
            "filtro": {
                "buscaGeral": summary_search_prompt.strip(),
                "todasPalavras": "",
                "quaisquerPalavras": "",
                "semPalavras": "",
                "trechoExato": "",
                "atualizacaoDesde": "",
                "atualizacaoAte": "",
                "cancelados": incluir_cancelados,
                "ordenacao": "Text",
                "nr": numero.strip(),
                "pagina": max(desired_page, 1),  # both sides are 1-based
                "tamanhoPagina": _RESULTS_PER_PAGE,
                "orgaos": orgaos,
                "tipos": tipos,
            }
        }

        _LOGGER.info(
            "BNP research: q=%r nr=%r courts=%d species=%d page=%d",
            summary_search_prompt,
            numero,
            len(orgaos),
            len(tipos),
            desired_page,
        )

        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=_HTTP_TIMEOUT,
                    follow_redirects=True,
                ) as client:
                    response = await client.post(
                        f"{_BASE_URL}/precedentes", headers=_HEADERS, json=body
                    )

                if response.status_code == _HTTP_BAD_REQUEST:
                    # The API's 400 body is an opaque "Requisição inválida".
                    raise RuntimeError(
                        "BNP: requisição rejeitada (400) — provável filtro "
                        "inválido (tribunal ou espécie inexistente)."
                    )

                response.raise_for_status()
                return cls._parse_results(response.json())

            except (httpx.HTTPError, RuntimeError) as exc:
                last_error = exc
                _LOGGER.warning(
                    "BNP attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc
                )
                # A 400 won't fix itself on retry — fail fast.
                if isinstance(exc, RuntimeError):
                    raise

        raise RuntimeError(
            f"BNP research failed after {_MAX_RETRIES} attempts"
        ) from last_error
