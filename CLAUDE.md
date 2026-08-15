# CLAUDE.md — jurismcp

MCP de Pesquisa Jurisprudencial. Scraping direto nos sites oficiais.

## O que é

Servidor MCP que pesquisa jurisprudência em 7 fontes e devolve metadados + ementa + link:

- **STJ** — HTTP POST direto ao SCON (sem browser)
- **STF** e **TST** — browser headless via patchright/Chromium
- **TJES** — REST API
- **LexML** — HTTP scrape, **fonte federada multi-tribunal** (agrega STF/STJ/TST/TSE/STM/TRFs/TJs numa só query, para amplitude/descoberta). Endpoint `lexml.gov.br/busca/search` (a SRU/XML legada foi descontinuada). Request: `LexmlLegalPrecedentsRequest`; retorna metadados + ementa + link URN.
- **Jurisprudencias.ai** — API REST multi-tribunal **ADICIONAL e OPCIONAL** (agregador terceirizado, não é portal oficial). Ativa só quando a env var `JURISPRUDENCIAS_AI_TOKEN` está setada (token `jur_...` de jurisprudencias.ai/api-tokens); sem token, retorna erro explicativo e NÃO afeta as outras fontes. Cobre TJs estaduais (TJSP/TJRS/TJMG/TJPR/TJSC/TJRJ/TJCE/TJGO/TJMA/TJMT), TRF3/TRF4 e **CARF** (fiscal) — **não cobre TJES** (use a tool dedicada). Request: `JurisprudenciasAiLegalPrecedentsRequest` (campo obrigatório `court` + `summary`). Endpoint `jurisprudencias.ai/api/v1/courts/{court}/decisions`. Quota grátis apertada (5 buscas/dia); pensada para precedente persuasivo sob demanda, não para o motor paralelo.

- **BNP/CNJ** — API REST pública SEM autenticação, **precedentes QUALIFICADOS de 60+ tribunais** (súmulas, SV, temas RG/RR, IRDR, IAC, IRR, PUIL, OJ, ADI/ADC/ADO/ADPF de STF/STJ/TST/STM/TNU/27 TJs/6 TRFs/24 TRTs), cada um com a situação viva. Devolve a TESE fixada, não ementa/inteiro teor. Request: `BnpLegalPrecedentsRequest` (`summary` + opcionais `tribunal`, `especie`, `numero`, `incluir_cancelados`). Endpoint `pangeabnp.pdpj.jus.br/api/v1/precedentes` (POST). Quirks: API não documentada (contrato por inspeção 08/2026); `orgaos`/`tipos` vazios → 400 opaco (listas sempre explícitas; órgãos via `GET /parametros` com cache de processo + fallback hardcoded); em SUM/SV o enunciado vem no campo `questao` (promoção só nessas espécies); teses-placebo ("não informado") viram "(ainda não publicada no BNP)" mas o item é MANTIDO; `situacao` é vocabulário aberto, exibida verbatim; portal SPA sem deep link por precedente.

## Arquitetura

- `src/jurismcp/domain/` — `stf.py`, `stj.py`, `tst.py`, `tjes.py`, `lexml.py`, `jurisprudencias_ai.py`, `bnp.py`
- `src/jurismcp/presentation/mcp.py` — entry point
- O switch `BaseLegalPrecedent.requires_browser` decide HTTP vs browser por fonte.
- Tools de tribunal único carregam só `summary`+`page`; tools multi-tribunal (Jurisprudencias.ai, BNP) carregam campos extras (`court`; `tribunal`/`especie`/`numero`/`incluir_cancelados`) que o dispatcher repassa via `**extra` a `research()` — fontes de tribunal único não são afetadas (recebem `**{}`).

## Adding a new source

Passo-a-passo (o exemplar mais recente é o `bnp.py`; para fonte autenticada/opt-in, o `jurisprudencias_ai.py`):

1. **`src/jurismcp/domain/<fonte>.py`** — `class <Fonte>LegalPrecedent(BaseLegalPrecedent)`:
   - `requires_browser: ClassVar[bool] = False` para HTTP/JSON/HTML direto (só STF/TST usam browser);
   - docstring de módulo em inglês documentando as quirks de integração descobertas ao vivo;
   - `_parse_results(cls, data) -> list[Self]` **puro, sem I/O** (é o que os testes offline exercitam);
   - `research()` com `@override @classmethod`, assinatura `(cls, browser, *, summary_search_prompt, desired_page=1, ...)` — parâmetros extras com default (ex.: `court`, `tribunal`);
   - resiliência da casa: `_MAX_RETRIES = 2`, timeout 30s, `httpx.AsyncClient` DENTRO do loop de retry, warning por tentativa, `RuntimeError(...) from last_error` no fim, UA de navegador.
2. **`src/jurismcp/presentation/mcp.py`** — import; `class <Fonte>LegalPrecedentsRequest(BaseLegalPrecedentsRequest)` (o NOME da classe vira o nome da tool e o prefixo da mensagem `[ERRO] <FONTE>:`; o docstring PT-BR vira a description); estender a união `Final[...]` de `_TOOLS_AND_MODELS` e acrescentar o par `(Request, Precedent)` na lista. Nada muda no dispatcher.
3. **Testes** — fixture inline + classe `Test<Fonte>ParseResults` em `tests/test_parsers.py` (offline); incluir a classe no parametrize de `test_research_http_legal_precedents` em `tests/test_domain.py` (rede); opcional: `pytest.param` no `test_call_tool` de `tests/test_presentation.py` se a tool tiver campos extras.
4. **Docs** — tabela + lista de tools no `README.md` (e `README.br.md`); bullet na lista de fontes deste arquivo.

Regra de idioma: descrições de tools/campos em PT-BR; código, comentários e docstrings de módulo em inglês.

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
