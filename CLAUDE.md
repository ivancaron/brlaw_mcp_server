# CLAUDE.md — jurismcp

MCP de Pesquisa Jurisprudencial. Scraping direto nos sites oficiais.

## O que é

Servidor MCP que pesquisa jurisprudência em 5 fontes e devolve metadados + ementa + link:

- **STJ** — HTTP POST direto ao SCON (sem browser)
- **STF** e **TST** — browser headless via patchright/Chromium
- **TJES** — REST API
- **LexML** — HTTP scrape, **fonte federada multi-tribunal** (agrega STF/STJ/TST/TSE/STM/TRFs/TJs numa só query, para amplitude/descoberta). Endpoint `lexml.gov.br/busca/search` (a SRU/XML legada foi descontinuada). Request: `LexmlLegalPrecedentsRequest`; retorna metadados + ementa + link URN.
- **Jurisprudencias.ai** — API REST multi-tribunal **ADICIONAL e OPCIONAL** (agregador terceirizado, não é portal oficial). Ativa só quando a env var `JURISPRUDENCIAS_AI_TOKEN` está setada (token `jur_...` de jurisprudencias.ai/api-tokens); sem token, retorna erro explicativo e NÃO afeta as outras fontes. Cobre TJs estaduais (TJSP/TJRS/TJMG/TJPR/TJSC/TJRJ/TJCE/TJGO/TJMA/TJMT), TRF3/TRF4 e **CARF** (fiscal) — **não cobre TJES** (use a tool dedicada). Request: `JurisprudenciasAiLegalPrecedentsRequest` (campo obrigatório `court` + `summary`). Endpoint `jurisprudencias.ai/api/v1/courts/{court}/decisions`. Quota grátis apertada (5 buscas/dia); pensada para precedente persuasivo sob demanda, não para o motor paralelo.

## Arquitetura

- `src/jurismcp/domain/` — `stf.py`, `stj.py`, `tst.py`, `tjes.py`, `lexml.py`, `jurisprudencias_ai.py`
- `src/jurismcp/presentation/mcp.py` — entry point
- O switch `BaseLegalPrecedent.requires_browser` decide HTTP vs browser por fonte.
- Tools de tribunal único carregam só `summary`+`page`; tools multi-tribunal (Jurisprudencias.ai) carregam um campo extra (`court`) que o dispatcher repassa via `**extra` a `research()` — fontes de tribunal único não são afetadas (recebem `**{}`).

## Comandos

```bash
uv run serve                      # inicia o servidor MCP (entry point [project.scripts])
uv run pytest                     # testes
uv run ruff check                 # lint
uv run basedpyright               # type check
uv run patchright install chromium  # deps do browser (STF/TST)
```

- **Pacote:** gerenciado com `uv`.
- **Log de erros:** `mcp.log` na raiz do projeto (WARNING e acima).
