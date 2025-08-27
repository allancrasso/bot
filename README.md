# Bot de Busca e Ingestão de Documentos

[![Status](https://img.shields.io/badge/status-beta-orange)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

## Visão geral

Este repositório contém um conjunto de scripts Python para **ingestão, indexação (por embeddings) e busca semântica** sobre documentos, com integração a LLMs para geração de 
respostas humanizadas. O código aqui publicado não contém chaves, senhas nem caminhos locais — e é adequado para execução local ou em ambientes controlados.

Casos de uso típicos:
- Central de atendimento que sugere respostas a partir de documentação corporativa.
- Pipeline de ingestão de documentos (`.docx`) para indexação semântica.
- Automação de fila de pendências quando a base de conhecimento não responde uma pergunta.

---

## Demonstração rápida

1. Usuário faz uma pergunta via GUI → sistema tenta encontrar correspondência por palavra-chave.  
2. Se não houver correspondência, calcula embedding da pergunta e faz busca por similaridade com embeddings por parágrafo.  
3. Se encontrar trecho relevante, pede ao LLM para gerar uma resposta humanizada baseada nesse trecho e apresenta ao usuário.  
4. Se não houver resultado suficiente, gera uma pendência (resumo via agente local, p.ex. Ollama) para análise humana.

---

## Funcionalidades principais

- Interface Desktop (Tkinter) para consulta por categoria / subcategoria.  
- Ingestão automática de documentos: download `.docx` → extração de texto → geração de embedding (OpenAI) → persistência em PostgreSQL.  
- Processamento granular por parágrafo para busca semântica mais precisa.  
- Cache local simples para reduzir chamadas externas.  
- Fallback que submete pendências a um agente local (ex.: Ollama) e grava para revisão.

---

## Estrutura de arquivos

- `app_sanitizado.py` — GUI em Tkinter para consulta (entrada do usuário, busca, exibição de respostas).  
- `ingest_sanitizado.py` — baixa `.docx`, gera embedding do documento e grava `documento` + `documento_embedding` no banco.  
- `processar_documentos_sanitizado.py` — gera embeddings por parágrafo e grava em `documento_paragrafo_embedding`.  
- `salvar_pendencia_sanitizado.py` — gera resumo via Ollama e grava pendência em `assunto_pendente`.  
- `sanitize_repo.py` *(opcional)* — utilitário para remover padrões sensíveis no repositório antes do commit.  
- `.env.example` — exemplo das variáveis de ambiente necessárias (sem valores reais).  
- `requirements.txt` — dependências Python.  
- `.gitignore` — padrões de arquivos a ignorar (ex.: `.env`, caches).  
- `.pre-commit-config.yaml` *(opcional)* — hooks para detectar segredos antes do commit.  
- `LICENSE` — arquivo de licença (recomendo MIT).  
- `README.md` — este arquivo.

---

## Requisitos

- Python 3.9+  
- PostgreSQL com as tabelas necessárias (esquema com tabelas referidas nos scripts)  
- Chave OpenAI válida (ou outro provedor de embeddings/LLM configurado)  
- (Opcional) Ollama para agente local de resumo

---

## Variáveis de ambiente (mínimas)

> **Importante:** não coloque chaves no repositório. Use `.env` local (ignorando-o no `.gitignore`) ou variáveis de ambiente no ambiente de execução.

- `OPENAI_API_KEY` — chave para OpenAI (embeddings / chat)  
- `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT` — credenciais PostgreSQL  
- `DOCUMENT_URL` — (quando usar `ingest`) URL do `.docx` para ingestão  
- `SECONDARY_AGENT_PATH` — caminho para script de fallback (opcional)  
- `OLLAMA_MODEL` — modelo local do Ollama (opcional)  
- `ARQUIVO_LOCAL` — nome do arquivo temporário de download (opcional)
