"""Unit tests for the parsing logic of the V3 jurismcp upgrade.

These tests do NOT require network access — they exercise pure parsers and
helpers added to support the `full_text`, `full_text_url`, `relator_original`
and `divergencia_vencedora` fields. Network-dependent integration tests live
in `test_domain.py` and may flap depending on each court's portal status.
"""

from __future__ import annotations

import textwrap

from jurismcp.domain.lexml import LexmlLegalPrecedent
from jurismcp.domain.stj import _STJ_BASE, StjLegalPrecedent
from jurismcp.domain.tjes import (
    TjesLegalPrecedent,
    _build_and_query,
    _detect_winning_dissent,
)


# ---------------------------------------------------------------------------
# TJES — `_build_and_query` (AND semantics fix)
# ---------------------------------------------------------------------------


class TestBuildAndQuery:
    """The pje2g core defaults to OR; plain multi-word queries must be
    rewritten to required-term AND (+term) so they don't flood with documents
    matching only the common words."""

    def test_plain_multiword_becomes_required_terms(self) -> None:
        assert (
            _build_and_query("turismo de aventura responsabilidade")
            == "+turismo +aventura +responsabilidade"
        )

    def test_stopwords_and_connectors_are_dropped(self) -> None:
        # "de" must NOT become "+de" (analyzer drops it -> would zero the search)
        out = _build_and_query("responsabilidade do estado")
        assert out == "+responsabilidade +estado"
        assert "+do" not in out

    def test_single_distinctive_term_left_untouched(self) -> None:
        # Nothing to AND; single-term OR already ranks correctly.
        assert _build_and_query("tirolesa") == "tirolesa"

    def test_quoted_phrase_is_advanced_and_untouched(self) -> None:
        q = '"turismo de aventura"'
        assert _build_and_query(q) == q

    def test_explicit_operators_left_untouched(self) -> None:
        assert _build_and_query("dano AND moral") == "dano AND moral"
        assert _build_and_query("+rafting acidente") == "+rafting acidente"
        assert _build_and_query("turismo -aventura") == "turismo -aventura"

    def test_hyphenated_word_is_not_mistaken_for_operator(self) -> None:
        # "boia-cross" must not trip the +/- advanced detector.
        assert _build_and_query("boia-cross acidente") == "+boia-cross +acidente"

    def test_empty_query_returns_empty(self) -> None:
        assert _build_and_query("   ") == ""

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
# STJ — `_parse_modern_template` (post-2025 SCON refresh)
# ---------------------------------------------------------------------------


_STJ_MODERN_FIXTURE = textwrap.dedent(
    """\
    <html><body>
    <div class="listaresumida">
      <div class="row clsHeaderDocumento"><div class="col">Acordaos</div></div>
      <div class="listadocumentos">
        <div class="row itemlistadocumentos p-2">
          <div class="col-sm-1"><h4>1</h4></div>
          <div class="col-sm-3">
            <h4>Processo</h4>
            <div>
              <a href="/SCON/jurisprudencia/doc.jsp?ementa=CONSUMIDOR&b=ACOR&i=1">REsp&nbsp;1896379</a>
            </div>
            <div class="small">(ACORDAO)</div>
            <div>Ministro OG FERNANDES</div>
            <div>DJe 13/12/2021</div>
            <div>Decisao: 21/10/2021</div>
          </div>
          <div class="col-sm-8">
            <div class="indicaIAC">INCIDENTE DE ASSUNCAO DE COMPETENCIA</div>
            <h4>Ementa</h4>
            <div class="clsResumoEmenta">
              <!-- Campo TEMA: 1. Tema Repetitivo 10 -->
              ...<br>RECURSO PROVIDO.
            </div>
            <div class="clsEmentaCompleta">
              PROCESSUAL CIVIL. RECURSO ESPECIAL. <span class=highlightBrs>CONSUMIDOR</span>.<br>RECURSO PROVIDO.
            </div>
          </div>
        </div>
        <div class="row itemlistadocumentos p-2">
          <div class="col-sm-1"><h4>2</h4></div>
          <div class="col-sm-3">
            <h4>Processo</h4>
            <div>
              <a href="/SCON/jurisprudencia/doc.jsp?ementa=CONSUMIDOR&i=2">REsp&nbsp;1903920</a>
            </div>
            <div class="small">(ACORDAO)</div>
            <div>Ministra NANCY ANDRIGHI</div>
            <div>DJe 01/04/2022</div>
            <div>Decisao: 22/03/2022</div>
          </div>
          <div class="col-sm-8">
            <h4>Ementa</h4>
            <div class="clsEmentaCompleta">
              CONSUMIDOR. RESPONSABILIDADE OBJETIVA.<br>SUMULA 297/STJ.
            </div>
          </div>
        </div>
      </div>
    </div>
    </body></html>
    """
)


class TestStjModernTemplateParser:
    """SCON refreshed its results page in 2025-2026. Each acordao is now
    inside ``<div class="row itemlistadocumentos">`` and the full ementa
    lives in ``<div class="clsEmentaCompleta">``. The parser must extract
    each block, build the metadata header, and use the doc.jsp href as
    full_text_url."""

    def test_parses_two_results_from_modern_template(self) -> None:
        results = StjLegalPrecedent._parse_ementas(_STJ_MODERN_FIXTURE)
        assert len(results) == 2

        first, second = results

        # First acordao
        assert "REsp 1896379" in first.summary
        assert "Ministro OG FERNANDES" in first.summary
        assert "DJe 13/12/2021" in first.summary
        assert "INCIDENTE DE ASSUNCAO DE COMPETENCIA" in first.summary
        # Ementa text (highlight span unwrapped, comment stripped, <br> -> \n)
        assert "PROCESSUAL CIVIL. RECURSO ESPECIAL. CONSUMIDOR" in first.summary
        assert "Campo TEMA" not in first.summary  # comment removed
        assert "highlightBrs" not in first.summary  # span unwrapped
        # full_text_url uses doc.jsp absolute URL
        assert first.full_text_url is not None
        assert first.full_text_url.startswith(f"{_STJ_BASE}/SCON/jurisprudencia/doc.jsp")

        # Second acordao (no indicador, no resumo block — only complete ementa)
        assert "REsp 1903920" in second.summary
        assert "Ministra NANCY ANDRIGHI" in second.summary
        assert "SUMULA 297/STJ" in second.summary
        assert second.full_text_url is not None

    def test_metadata_header_uses_brackets(self) -> None:
        """Metadata is prepended as ``[Processo: ... | Relator(a): ...]\\n``"""
        results = StjLegalPrecedent._parse_ementas(_STJ_MODERN_FIXTURE)
        assert results[0].summary.startswith("[Processo: REsp 1896379")
        assert "| Classe: ACORDAO" in results[0].summary

    def test_modern_template_takes_precedence_over_legacy(self) -> None:
        """When both templates' markers coexist (unlikely), modern wins."""
        hybrid = (
            '<html><body>'
            '<a name="DOC1"></a>'
            '<div class="documento">'
            '<textarea id="textSemformatacao1">Ementa legada</textarea>'
            '</div>'
            + _STJ_MODERN_FIXTURE
            + '</body></html>'
        )
        results = StjLegalPrecedent._parse_ementas(hybrid)
        # 2 results from modern; legacy block ignored
        assert len(results) == 2
        assert all("Ementa legada" not in r.summary for r in results)

    def test_falls_back_to_resumo_when_no_complete_ementa(self) -> None:
        html = textwrap.dedent(
            """\
            <html><body>
            <div class="row itemlistadocumentos p-2">
              <div class="col-sm-3">
                <h4>Processo</h4>
                <div><a href="/SCON/jurisprudencia/doc.jsp?i=99">REsp 999</a></div>
                <div class="small">(ACORDAO)</div>
                <div>Ministro X</div>
                <div>DJe 01/01/2024</div>
              </div>
              <div class="col-sm-8">
                <h4>Ementa</h4>
                <div class="clsResumoEmenta">Resumo do acordao apenas.</div>
              </div>
            </div>
            </body></html>
            """
        )
        results = StjLegalPrecedent._parse_ementas(html)
        assert len(results) == 1
        assert "Resumo do acordao apenas" in results[0].summary

    def test_html_inline_cleaning_decodes_entities(self) -> None:
        html = (
            '<div class="row itemlistadocumentos p-2">'
            '<div class="col-sm-3"><h4>Processo</h4>'
            '<div><a href="/SCON/x">REsp&nbsp;1</a></div>'
            '<div class="small">(ACORDAO)</div></div>'
            '<div class="col-sm-8">'
            '<div class="clsEmentaCompleta">'
            'TESTE &amp; ENTIDADE &quot;ASPAS&quot; &nbsp;NBSP.'
            '</div>'
            '</div></div>'
        )
        results = StjLegalPrecedent._parse_ementas(html)
        assert len(results) == 1
        assert "TESTE & ENTIDADE" in results[0].summary
        assert '"ASPAS"' in results[0].summary
        assert "&amp;" not in results[0].summary
        assert "&nbsp;" not in results[0].summary


# ---------------------------------------------------------------------------
# LexML — `_parse_results` (federated XTF HTML search)
# ---------------------------------------------------------------------------


# Mirrors the live LexML XTF markup: each result is a
# <div id="main_N" class="docHit"><table> with label/value rows across
# <td class="col2"><b>LABEL</b></td><td class="col3">VALUE</td> cells.
# Labels carry trailing non-breaking spaces (&#160;) and the ementa carries
# <span class="hit"> highlight markup — both must be cleaned away.
_LEXML_FIXTURE = textwrap.dedent(
    """\
    <html><body>
    <td class="docHit"><div id="main_1" class="docHit"><table>
      <tr><td class="col1"><b>1</b></td><td class="col2"><b>Localidade&#160;&#160;</b></td><td class="col3">Distrito Federal</td><td class="col4"> </td></tr>
      <tr><td class="col1"> </td><td class="col2"><b>Autoridade&#160;&#160;</b></td><td class="col3">Tribunal de Justiça do Distrito Federal e dos Territórios. 5ª Turma Cível</td><td class="col4"> </td></tr>
      <tr><td class="col1"> </td><td class="col2"><b>Título&#160;&#160;</b></td><td class="col3"><a href="/urn/urn:lex:br;distrito.federal:tribunal.justica.distrito.federal.territorios;turma.civel.5:acordao:2009-11-04;394803">Acórdão nº 394803 do Processo nº20060110390196apc</a>&#160;</td><td class="col4"> </td></tr>
      <tr><td class="col1"> </td><td class="col2"><b>Data&#160;&#160;</b></td><td class="col3">04/11/2009</td><td class="col4"> </td></tr>
      <tr><td class="col1"> </td><td class="col2"><b>Ementa&#160;&#160;</b></td><td class="col3">CIVIL. EXECUÇÃO DE <span class="hit">ALIMENTOS</span> PROVISÓRIOS. POSSIBILIDADE.</td><td class="col4"> </td></tr>
    </table></div></td>
    <td class="docHit"><div id="main_2" class="docHit"><table>
      <tr><td class="col1"><b>2</b></td><td class="col2"><b>Localidade&#160;&#160;</b></td><td class="col3">Federal</td><td class="col4"> </td></tr>
      <tr><td class="col1"> </td><td class="col2"><b>Autoridade&#160;&#160;</b></td><td class="col3">Superior Tribunal de Justiça</td><td class="col4"> </td></tr>
      <tr><td class="col1"> </td><td class="col2"><b>Título&#160;&#160;</b></td><td class="col3"><a href="/urn/urn:lex:br:superior.tribunal.justica:acordao:2020-05-12;1896526">REsp 1896526</a></td><td class="col4"> </td></tr>
      <tr><td class="col1"> </td><td class="col2"><b>Data&#160;&#160;</b></td><td class="col3">12/05/2020</td><td class="col4"> </td></tr>
    </table></div></td>
    </body></html>
    """
)


class TestLexmlParseResults:
    """LexML federates jurisprudence from many courts. Records expose
    metadata (localidade, autoridade, título, data) plus an ementa when
    indexed, and a URN link to the source. The parser builds a metadata
    header + body summary, and fills ``court``/``urn``/``full_text_url``."""

    def test_parses_two_federated_results(self) -> None:
        results = LexmlLegalPrecedent._parse_results(_LEXML_FIXTURE)
        assert len(results) == 2

        first, second = results

        # First: TJDFT, with ementa
        assert first.court == (
            "Tribunal de Justiça do Distrito Federal e dos Territórios. "
            "5ª Turma Cível"
        )
        assert "Tribunal/Órgão:" in first.summary
        assert "Data: 04/11/2009" in first.summary
        assert "Acórdão nº 394803" in first.summary
        # ementa cleaned: highlight span unwrapped, kept text
        assert "EXECUÇÃO DE ALIMENTOS PROVISÓRIOS" in first.summary
        assert "<span" not in first.summary
        # urn + resolver link
        assert first.urn == (
            "urn:lex:br;distrito.federal:tribunal.justica.distrito.federal."
            "territorios;turma.civel.5:acordao:2009-11-04;394803"
        )
        assert first.full_text_url == f"https://www.lexml.gov.br/urn/{first.urn}"

        # Second: STJ, no ementa row — summary still built from título + meta
        assert second.court == "Superior Tribunal de Justiça"
        assert "REsp 1896526" in second.summary
        assert second.urn is not None
        assert second.urn.startswith("urn:lex:br:superior.tribunal.justica")

    def test_label_nbsp_is_normalized(self) -> None:
        """Trailing &#160; on labels must not break field-key matching."""
        results = LexmlLegalPrecedent._parse_results(_LEXML_FIXTURE)
        # If labels weren't normalized, court/data would be missing.
        assert all(r.court for r in results)

    def test_returns_empty_when_no_dochit_blocks(self) -> None:
        html = (
            "<html><body><div class='results'>"
            "Nenhum documento encontrado</div></body></html>"
        )
        assert LexmlLegalPrecedent._parse_results(html) == []


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
