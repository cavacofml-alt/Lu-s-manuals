# Modelo — Documento de alterações por release

Modelo para o documento descrito em `SHAREPOINT.md` §7.2. Copiar para Word, preencher,
publicar na biblioteca indexada com `TipoDocumento = Release notes` e `Estado = Em vigor`.

---

## Porque é que este documento tem esta forma

Três decisões de estrutura, cada uma contra o instinto natural de quem escreve notas de
versão.

**Organizado por procedimento, não por release.** O instinto é fazer um capítulo por
versão. Mas as pessoas não perguntam "o que mudou na 7.4?" — perguntam "como faço o
check-in ADL?". Se o texto estiver debaixo de um cabeçalho "Release 7.4", o pedaço
recuperado para "check-in" chega ao assistente sem dizer de que procedimento fala. Uma
secção por procedimento, com as releases lá dentro, é recuperável pelas duas perguntas.

A pergunta ao nível da release responde-se com a tabela-resumo no topo, que é curta e cabe
num pedaço só.

**Escrito no que a pessoa faz de diferente**, não no que o sistema mudou por dentro.
"Removido o passo de validação síncrona no serviço de check-in" não ajuda ninguém.
"Deixou de ser preciso confirmar manualmente" ajuda.

**Diz também o que *não* mudou**, onde houver risco de confusão. É invulgar e é
deliberado: sem essa frase, tanto uma pessoa como um assistente inferem que, se algo
mudou perto, também mudou ali.

---

## Modelo

### Cabeçalho

```
Alterações por release — <Sistema>
Documento de referência · Atualizado em <data> · Responsável: <nome>
Cobre as releases <7.1> a <7.4>.
```

### Tabela-resumo

Uma linha por release. É o que responde a "o que mudou na 7.4?".

| Release | Em vigor desde | Procedimentos afetados |
|---|---|---|
| 7.4 | 2026-03-01 | Check-in ADL · Reprocessamento de PNL |
| 7.3 | 2025-10-15 | Consulta de estados |
| 7.2 | 2025-06-01 | Sem alterações de procedimento |

### Uma secção por procedimento alterado

Repetir esta estrutura. **Cada secção tem de se explicar sozinha** — quem a ler fora do
documento não sabe de que sistema se trata se não estiver escrito ali.

```
## Como fazer o check-in ADL — o que mudou

O procedimento de check-in ADL mudou na release 7.4.

Desde a 7.4:
  <descrição do que a pessoa faz hoje, em passos se aplicável>

Até à 7.3 (já não aplicável):
  <o que se fazia antes>

O que mudou em concreto:
  <uma frase: o que desapareceu, apareceu ou passou a ser diferente>

Porquê:
  <se for conhecido e útil; caso contrário, omitir>

Não mudou:
  <o que se mantém, onde houver risco de alguém assumir que também mudou>

Onde está documentado:
  <Manual, secção> — release em vigor
```

---

## Exemplo preenchido

> ## Como fazer o check-in ADL — o que mudou
>
> O procedimento de check-in ADL mudou na release 7.4.
>
> **Desde a 7.4:**
> 1. Abrir o ecrã de check-in ADL.
> 2. Introduzir o identificador do voo.
> 3. Clicar em **Confirmar**. O sistema valida e conclui o check-in automaticamente.
>
> **Até à 7.3 (já não aplicável):** depois de clicar em Confirmar, era apresentado um ecrã
> de validação onde era preciso confirmar manualmente uma segunda vez.
>
> **O que mudou em concreto:** o segundo passo de confirmação manual foi removido. O
> check-in ADL conclui-se agora com uma única confirmação.
>
> **Não mudou:** o tratamento de erros de validação. Se o identificador do voo for
> inválido, a mensagem e o procedimento de correção são os mesmos da 7.3.
>
> **Onde está documentado:** Manual de Check-in ADL, secção "Procedimento de Check-in" —
> release 7.4.

Repare no que este exemplo faz e que as notas de versão habituais não fazem:

- diz **"check-in ADL"** em todas as frases importantes, e não "o processo" ou "o
  procedimento" — é isso que torna cada pedaço encontrável;
- o cabeçalho é a pergunta que a pessoa faz;
- a versão em vigor vem primeiro e a antiga está marcada como não aplicável, para que um
  assistente que recupere só metade da secção recupere a metade certa;
- a frase **"Não mudou"** impede a inferência errada de que o tratamento de erros também
  mudou.

---

## A evitar

| Em vez de | Escrever |
|---|---|
| "Bug 4521 — validação duplicada corrigida" | "Deixou de ser preciso confirmar duas vezes no check-in ADL" |
| "Refactorização do módulo de check-in" | Nada. Se não muda o que a pessoa faz, não entra neste documento |
| "Ver release notes 7.4 para detalhes" | O detalhe, aqui. Uma remissão não é recuperável |
| "O processo foi simplificado" | O que era, o que é, e a diferença |
| Um capítulo por release | Uma secção por procedimento |

E uma regra que evita o pior erro possível: **este documento não substitui os manuais.**
Descreve alterações e aponta para onde o procedimento está documentado a sério. Se começar
a conter o procedimento completo, passa a ser uma segunda fonte que se desatualiza sozinha
— e duas fontes que discordam são piores do que uma fonte incompleta.

---

## Onde ir buscar o conteúdo

Por ordem de fiabilidade:

1. **Notas de versão do fornecedor ou da equipa de desenvolvimento** — traduzidas de
   linguagem técnica para linguagem de quem usa. É tradução, não cópia.
2. **Quem deu formação na altura da migração.** Essa pessoa sabe exatamente o que teve de
   explicar às pessoas, que é precisamente o que mudou na prática.
3. **Pedidos de apoio nas semanas a seguir a cada release.** As perguntas que apareceram de
   repente marcam o que mudou e não estava claro.
4. **Comparar os manuais das duas releases.** O mais lento, mas o mais completo. Só vale a
   pena para os procedimentos que as três primeiras fontes assinalarem.

Se só tiver tempo para uma coisa: **comece pela release atual e pela anterior.** As
alterações entre a 7.1 e a 7.2 já não confundem ninguém; as da 7.3 para a 7.4 confundem
todos os dias.
