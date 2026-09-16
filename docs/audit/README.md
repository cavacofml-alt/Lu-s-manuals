# Audit — links estáveis

Esta pasta existe para que a revisão externa não dependa de copiar ficheiros à mão.
O repositório é **público**, portanto estes URLs podem ser lidos diretamente por uma
ferramenta externa.

Todos os links apontam para o ramo `claude/new-session-hqskuv`, que é o ramo de
desenvolvimento e o ramo por omissão do repositório.

## Para colar numa auditoria

| O quê | Link (raw, legível por máquina) |
|---|---|
| **Bundle de auditoria** — estado + matriz + código sob revisão, num só ficheiro | https://raw.githubusercontent.com/cavacofml-alt/Lu-s-manuals/claude/new-session-hqskuv/docs/audit/BUNDLE.md |
| **Arquitetura** — o desenho e o raciocínio | https://raw.githubusercontent.com/cavacofml-alt/Lu-s-manuals/claude/new-session-hqskuv/docs/ARCHITECTURE.md |
| **Matriz de egress** — gerada por execução do guard real | https://raw.githubusercontent.com/cavacofml-alt/Lu-s-manuals/claude/new-session-hqskuv/EGRESS.md |

Versões navegáveis (com realce de sintaxe), para leitura humana:

- https://github.com/cavacofml-alt/Lu-s-manuals/blob/claude/new-session-hqskuv/docs/audit/BUNDLE.md
- https://github.com/cavacofml-alt/Lu-s-manuals/blob/claude/new-session-hqskuv/docs/ARCHITECTURE.md
- https://github.com/cavacofml-alt/Lu-s-manuals/blob/claude/new-session-hqskuv/EGRESS.md

## Como regenerar

```sh
make audit     # regenera docs/audit/BUNDLE.md a partir da árvore de trabalho
make egress    # regenera EGRESS.md executando o guard real
```

O bundle é carimbado com o commit e assinala se a árvore de trabalho tem alterações
por commitar — um bundle desatualizado fica visível em vez de passar despercebido.

## ⚠️ Este repositório é público

Consequência direta, e mais séria do que parece num projeto sobre documentação
confidencial: **nenhum manual real pode ser commitado aqui**. Três rondas de revisão
foram gastas a impedir que texto documental chegasse a um fornecedor de embeddings na
nuvem; um PDF commitado por engano seria uma divulgação maior e mais permanente do que
qualquer coisa que a política de egress previne.

O `.gitignore` bloqueia as pastas onde documentos reais aterram, e o CI recusa o build
se um PDF for adicionado. Os ficheiros de teste em `backend/tests/fixtures/` têm de ser
sintéticos ou públicos — nunca documentação interna.

Se o repositório tiver de continuar público, o corpus real vive fora dele.
Se o corpus tiver de viver aqui, o repositório passa a privado — e então estes links
deixam de funcionar para auditoria externa, e voltamos a colar ficheiros à mão.

## Correr sem PC local

`.devcontainer/` permite abrir o repositório em **GitHub Codespaces** (plano gratuito:
60 h/mês) e ter a stack a correr sem instalar nada. É a mesma `docker-compose.yml` que
correrá no PC local — não existe uma "versão cloud" a divergir da final.

1. No GitHub: **Code → Codespaces → Create codespace**
2. Esperar pelo `setup.sh` (Postgres, dependências, migrações)
3. `make test`

**Custos:** nada até ao STEP 5. Schema, ingestão, extração e indexação com embeddings
locais não usam APIs pagas. A partir das respostas, cada pergunta ao Claude custa
~€0,06.

**Os manuais reais não entram aqui.** Um Codespace é armazenamento de terceiros, tal
como o repositório é público. Documentos de teste não confidenciais apenas.
