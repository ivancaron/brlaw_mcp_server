# Jurismcp — Brazilian Law Research MCP Server

[🇧🇷 Leia em português](README.br.md)

A MCP (Model Context Protocol) server for agent-driven research on Brazilian law using official 
sources.

<a href="https://glama.ai/mcp/servers/@pdmtt/jurismcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@pdmtt/jurismcp/badge" alt="Brazilian Law Research Server MCP server" />
</a>

## Foreword
This server empowers models with scraping capacities, thus making research easier to anyone
legitimately interested in Brazilian legal matters.

This facility comes with a price: the risk of overloading the official sources' servers if misused.
Please be sure to keep the load on the sources to a reasonable amount.

## Architecture

Each court uses the most reliable access method available:

| Court | Method | Endpoint |
|-------|--------|----------|
| **STJ** | Direct HTTP POST | `processo.stj.jus.br/SCON/pesquisar.jsp` |
| **STF** | Headless browser (Chromium) | `jurisprudencia.stf.jus.br` |
| **TST** | Headless browser (Chromium) | `jurisprudencia.tst.jus.br` |
| **TJES** | Direct HTTP GET (REST API) | `sistemas.tjes.jus.br/consulta-jurisprudencia/api/search` |
| **LexML** (federated) | Direct HTTP GET (HTML scrape) | `lexml.gov.br/busca/search` |
| **Jurisprudencias.ai** (opt-in, multi-court) | Direct HTTP GET (JSON REST API, token) | `jurisprudencias.ai/api/v1/courts/{court}/decisions` |
| **BNP/CNJ** (qualified precedents, 60+ courts) | Direct HTTP POST (JSON REST API) | `pangeabnp.pdpj.jus.br/api/v1/precedentes` |

The STJ endpoint (`processo.stj.jus.br`) serves the same SCON search results as
`scon.stj.jus.br` but without Cloudflare Turnstile protection, enabling fast and
reliable access via direct HTTP requests with proper ISO-8859-1 form encoding.

The TJES endpoint exposes a public JSON API that returns each ruling's full
text (`acordao` field) on the same response as the summary, eliminating the
need for an extra request to obtain the inteiro teor.

**LexML** is the Brazilian government's federated legal-information portal: a
single query surfaces jurisprudence aggregated from many courts (STF, STJ, TST,
TSE, STM, the regional federal courts and the state courts of justice). It is the
breadth source — use it to discover precedents from courts without a dedicated
tool, and use the dedicated tools for depth in a specific court. Records carry
metadata, the ementa when indexed, and a `urn:lex` resolver link to the official
full text. The legacy SRU/XML endpoint was decommissioned, so results are scraped
from the server-rendered UTF-8 HTML of the XTF search; no browser is needed.

**BNP** (Banco Nacional de Precedentes, `bnp.pdpj.jus.br`) is the CNJ's official
registry of QUALIFIED precedents — súmulas, súmulas vinculantes, repercussão
geral and repetitive-appeal themes, IRDR/IAC/IRR, PUIL, OJ and abstract
constitutional review — federating 60+ courts (STF, STJ, TST, STM, TNU, all 27
state courts, the 6 TRFs and the 24 TRTs). Unlike the other sources it returns
each precedent's FIXED THESIS and live status (Vigente/Afetado/Cancelado/...),
not case-law ementas or full texts. The backing REST API is public and
unauthenticated, but undocumented — the contract was lifted by portal
inspection (aug/2026).

A new design switch, `BaseLegalPrecedent.requires_browser`, lets the dispatcher
pick HTTP vs. browser automatically per court, so adding a new HTTP-based court
needs no change to the dispatch logic.

## Requirements

- git
- uv (recommended) or Python >= 3.12
- Google Chrome (required for STF and TST; not needed for STJ)

## How to use

1. Clone the repository:
```bash
git clone https://github.com/pdmtt/jurismcp.git
```

2. Install the dependencies
```bash
uv run patchright install
```

3. Setup your MCP client (e.g. Claude Desktop):
```json
{
  "mcpServers": {
    "jurismcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/<path>/jurismcp",
        "run",
        "serve"
      ]
    }
  }
}
```

### Available Tools

- `StjLegalPrecedentsRequest`: Research legal precedents made by the National High Court of Brazil
  (STJ) that meet the specified criteria. Uses direct HTTP POST for fast, reliable access.
- `TstLegalPrecedentsRequest`: Research legal precedents made by the National High Labor Court of
  Brazil (TST) that meet the specified criteria.
- `StfLegalPrecedentsRequest`: Research legal precedents made by the Supreme Court (STF) that meet
  the specified criteria.
- `TjesLegalPrecedentsRequest`: Research legal precedents made by the Court of Justice of the State
  of Espírito Santo (TJES). Uses TJES public REST API.
- `LexmlLegalPrecedentsRequest`: Research **federated** jurisprudence aggregated by the LexML portal
  across many Brazilian courts at once. Best for breadth/discovery; returns metadata, the ementa
  when indexed, and a `urn:lex` link to the source. Uses a direct HTTP GET (no browser).
- `JurisprudenciasAiLegalPrecedentsRequest`: **Optional, opt-in** multi-court source backed by the
  Jurisprudencias.ai REST API (a third-party aggregator, not an official portal). Requires the
  `JURISPRUDENCIAS_AI_TOKEN` environment variable (a `jur_...` token from
  [jurisprudencias.ai/api-tokens](https://jurisprudencias.ai/api-tokens)); without it the tool
  returns a clear error and the other sources keep working. Takes a required `court` id (e.g.
  `tjsp`, `tjrs`, `tjmg`, `carf`, `trf4`) plus the search terms, and returns the ementa/excerpt,
  metadata and the official tribunal deep-link in `full_text_url`. Covers state courts (TJSP, TJRS,
  TJMG, TJPR, TJSC, TJRJ, TJCE, TJGO, TJMA, TJMT), TRF3/TRF4 and **CARF** — courts the dedicated
  scrapers don't reach in depth. It does **not** cover the TJES (use `TjesLegalPrecedentsRequest`
  for the home court). Direct HTTP GET (no browser). The free tier is limited (5 searches/day), so
  it is meant for on-demand persuasive-precedent lookups, not for high-volume parallel search.
- `BnpLegalPrecedentsRequest`: Research **qualified precedents** in the CNJ's Banco Nacional de
  Precedentes (BNP) — súmulas, súmulas vinculantes, RG/RR themes, IRDR, IAC, IRR, PUIL, OJ and
  ADI/ADC/ADO/ADPF from 60+ courts, each with its live status (Vigente/Afetado/Cancelado/...).
  Optional filters: `tribunal` (BNP sigla, e.g. `STJ`, `TJES`, `trf2`), `especie` (e.g. `SUM`,
  `RR`, `RG`, `IRDR`), `numero` (exact Tema/Súmula number) and `incluir_cancelados`. Returns the
  fixed thesis (and the submitted question when distinct), **not** ementas or full texts — use the
  dedicated court tools or LexML for those. Public unauthenticated REST API; no browser.

### Response Fields

Each tool returns a list of legal precedents. Beyond the canonical `summary` (ementa) field,
results may also expose the following optional fields when the source court provides the data:

| Field | Type | Populated by | Description |
|-------|------|--------------|-------------|
| `summary` | `str` | All | The ementa (mandatory). |
| `full_text` | `str \| None` | TJES | Integral text of the decision (relatório + voto + dispositivo). The TJES REST API ships this on the same response as the summary, so no extra request is needed. |
| `full_text_url` | `str \| None` | STJ, STF, TST | Absolute URL pointing to the inteiro teor. STJ returns a PDF directly (`/SCON/GetInteiroTeorDoAcordao?...`); STF returns a details page that hosts the PDF; TST returns the closest matching link found within each result block. |
| `relator_original` | `str \| None` | TJES | Original rapporteur's name when the decision was rendered by a winning dissent — situation in which the TJES API indexes the case by the redator (winning vote) instead of the original relator. |
| `divergencia_vencedora` | `bool` | TJES | `True` when the decision was rendered by a winning dissent. Defaults to `False`. |
| `court` | `str \| None` | LexML, BNP | Originating court/organ of a federated result, since these sources aggregate many courts in one response. |
| `urn` | `str \| None` | LexML | The `urn:lex:br:...` identifier of the document; pairs with `full_text_url` (the URN resolver link). |

All optional fields default to `None`/`False` when the court doesn't expose the data, so the change
is fully backwards compatible — existing consumers that don't read them keep working.

### Search Operators

Each court supports specific search operators for more precise queries. See the tool descriptions
for detailed syntax (e.g., `e`, `ou`, `não`, `adj`, `prox`, `$`, `?` for STJ; `E`, `OU`, `NÃO`,
`"..."`, `"..."~N`, `$`, `?` for STF). For TJES, terms are combined with implicit `AND`.

## Development

### Tooling

The project uses:
- Ruff for linting and formatting.
- BasedPyright for type checking.
- Pytest for testing.

### Language

Resources, tools and prompts related stuff must be written in Portuguese, because this project aims 
to be used by non-dev folks, such as lawyers and law students. 

Technical legal vocabulary is highly dependent on a country's legal tradition and translating it is 
no trivial task.

Development related stuff should stick to English as conventional, such as source code.

## License

This project is licensed under the MIT License - see the LICENSE file for details.