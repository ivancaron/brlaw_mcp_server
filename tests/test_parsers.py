"""Unit tests for the parsing logic of the V3 jurismcp upgrade.

These tests do NOT require network access — they exercise pure parsers and
helpers added to support the `full_text`, `full_text_url`, `relator_original`
and `divergencia_vencedora` fields. Network-dependent integration tests live
in `test_domain.py` and may flap depending on each court's portal status.
"""

from __future__ import annotations

import textwrap

from jurismcp.domain.stj import _STJ_BASE, StjLegalPrecedent
from jurismcp.domain.tjes import (
    TjesLegalPrecedent,
    _detect_winning_dissent,
)

# ---------------------------------------------------------------------------
# TJES — `_detect_winning_dissent`
# ---------------------------------------------------------------------------


class TestDetectWinningDissent:
    """The TJES REST API indexes acórdãos by the redator (winning vote), not
    the original relator. When divergence wins, we recover the original
    rapporteur from the acordão text."""

    def test_winning_dissent_detected_when_present(self) -> None:
        """If the acórdão has both VOTO VENCEDOR and a different relator
        in the composition line, returns the original relator + True."""
        acordao = textwrap.dedent(
            """
            APELACAO CIVEL n. 1234567-89.2024.8.08.0001
            VOTO VENCEDOR
            Relator: Desembargador Jose Paulo Calmon Nogueira da Gama
            Sessao Virtual de 01/09/25 a 05/09/25
            Composicao: JOSE PAULO CALMON NOGUEIRA DA GAMA - Relator /
            JANETE VARGAS SIMOES - Vogal
            """
        ).strip()

        rel_orig, divergencia = _detect_winning_dissent(
            acordao, magistrado_api="JANETE VARGAS SIMOES"
        )

        assert divergencia is True
        assert rel_orig is not None
        assert "Calmon" in rel_orig

    def test_no_dissent_when_acordao_has_no_voto_vencedor(self) -> None:
        """An ordinary acórdão (no divergence) returns (None, False)."""
        acordao = (
            "Apelacao Civel. Relator: Desembargador Helimar Pinto. "
            "Acordam os desembargadores em conhecer e dar provimento."
        )
        rel_orig, divergencia = _detect_winning_dissent(
            acordao, magistrado_api="HELIMAR PINTO"
        )
        assert rel_orig is None
        assert divergencia is False

    def test_no_dissent_when_relator_matches_magistrado(self) -> None:
        """If the acórdão has VOTO VENCEDOR but the relator IS the same
        person as `magistrado` (case insensitive), no dissent is reported."""
        acordao = (
            "VOTO VENCEDOR\n"
            "Relator: Desembargador Helimar Pinto\n"
            "Composicao: HELIMAR PINTO - Relator"
        )
        rel_orig, divergencia = _detect_winning_dissent(
            acordao, magistrado_api="HELIMAR PINTO"
        )
        assert rel_orig is None
        assert divergencia is False

    def test_empty_acordao_returns_none(self) -> None:
        rel_orig, divergencia = _detect_winning_dissent("", "anyone")
        assert rel_orig is None
        assert divergencia is False


# ---------------------------------------------------------------------------
# STJ — `_parse_ementas`
# ---------------------------------------------------------------------------


_STJ_RESULT_FIXTURE = textwrap.dedent(
    """\
    <html><body>
    <a name="DOC1"></a>
    <div class="documento">
      <div class="col clsIdentificacaoDocumento">RESP 2193519</div>
      <a href="javascript:inteiro_teor('/SCON/GetInteiroTeorDoAcordao?num_registro=202500224815&dt_publicacao=12/12/2025')">Inteiro Teor</a>
      <textarea id="textSemformatacao1">Ementa do primeiro acordao do STJ.</textarea>
    </div>
    <a name="DOC2"></a>
    <div class="documento">
      <div class="col clsIdentificacaoDocumento">RESP 2190210</div>
      <a href="javascript:inteiro_teor('/SCON/GetInteiroTeorDoAcordao?num_registro=202100249234&dt_publicacao=27/11/2025')">Inteiro Teor</a>
      <textarea id="textSemformatacao2">Ementa do segundo acordao do STJ.</textarea>
    </div>
    </body></html>
    """
)


class TestStjParseEmentas:
    """The STJ HTML response wraps each result in `<div class="documento">`
    and emits `inteiro_teor('/SCON/GetInteiroTeorDoAcordao?...')` calls
    next to each ementa. The parser must pair them up correctly."""

    def test_parses_ementa_and_full_text_url(self) -> None:
        results = StjLegalPrecedent._parse_ementas(_STJ_RESULT_FIXTURE)
        assert len(results) == 2

        first, second = results
        assert first.summary == "Ementa do primeiro acordao do STJ."
        assert first.full_text_url == (
            f"{_STJ_BASE}/SCON/GetInteiroTeorDoAcordao"
            "?num_registro=202500224815&dt_publicacao=12/12/2025"
        )

        assert second.summary == "Ementa do segundo acordao do STJ."
        assert second.full_text_url is not None
        assert "202100249234" in second.full_text_url
        assert "27/11/2025" in second.full_text_url

    def test_returns_empty_when_no_results(self) -> None:
        html = (
            "<html><body><div>Nenhum documento encontrado para esta pesquisa</div>"
            "</body></html>"
        )
        results = StjLegalPrecedent._parse_ementas(html)
        assert results == []

    def test_falls_back_to_plain_ementa_when_no_doc_blocks(self) -> None:
        """When the HTML has textareas but no `<a name="DOCN">` markers
        (legacy/edge case), parser falls back to plain ementa extraction
        with `full_text_url=None`."""
        html = (
            '<html><body>'
            '<textarea id="textSemformatacao1">Ementa solta sem bloco.</textarea>'
            '</body></html>'
        )
        results = StjLegalPrecedent._parse_ementas(html)
        assert len(results) == 1
        assert results[0].summary == "Ementa solta sem bloco."
        assert results[0].full_text_url is None


# ---------------------------------------------------------------------------
# Pydantic model — new fields are optional and serialise correctly
# ---------------------------------------------------------------------------


class TestPydanticFields:
    def test_tjes_default_field_values_are_none_or_false(self) -> None:
        p = TjesLegalPrecedent(summary="só ementa")
        assert p.full_text is None
        assert p.full_text_url is None
        assert p.relator_original is None
        assert p.divergencia_vencedora is False

    def test_tjes_serialises_with_dissent_metadata(self) -> None:
        p = TjesLegalPrecedent(
            summary="ementa",
            full_text="inteiro teor",
            relator_original="Calmon",
            divergencia_vencedora=True,
        )
        d = p.model_dump()
        assert d["divergencia_vencedora"] is True
        assert d["relator_original"] == "Calmon"
        assert d["full_text"] == "inteiro teor"
        assert d["full_text_url"] is None

    def test_stj_serialises_with_full_text_url(self) -> None:
        p = StjLegalPrecedent(
            summary="ementa",
            full_text_url="https://processo.stj.jus.br/SCON/GetInteiroTeor...",
        )
        d = p.model_dump()
        assert d["full_text_url"].startswith("https://processo.stj.jus.br")
        assert d["full_text"] is None
