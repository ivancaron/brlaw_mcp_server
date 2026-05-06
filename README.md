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

The STJ endpoint (`processo.stj.jus.br`) serves the same SCON search results as
`scon.stj.jus.br` but without Cloudflare Turnstile protection, enabling fast and
reliable access via direct HTTP requests with proper ISO-8859-1 form encoding.

The TJES endpoint exposes a public JSON API that returns each ruling's full
text (`acordao` field) on the same response as the summary, eliminating the
need for an extra request to obtain the inteiro teor.

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

All four fields default to `None`/`False` when the court doesn't expose the data, so the change is
fully backwards compatible — existing consumers that don't read them keep working.

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