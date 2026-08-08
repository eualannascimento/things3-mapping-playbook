---
name: things3-mapping-playbook
description: Cria, lê, atualiza, move, restaura e exclui itens do Things 3 (to-do, projeto, área, tag, heading, checklist-item) via o pacote Python things3, com dry-run, backup e verificação embutidos. Use quando o usuário pedir para organizar, criar, editar ou apagar tarefas/projetos no Things, checar o ambiente antes de automatizar, ou quando a operação puder ser destrutiva e precisar de garantia de que funcionou de verdade. Só funciona no macOS, com Things 3 instalado.
---

# things3-mapping-playbook

Biblioteca Python + CLI para Things 3, com a camada de garantia que a plataforma não tem: toda
escrita destrutiva é dry-run por padrão, faz backup antes, e verifica o resultado relendo o banco
— porque um código de retorno bem-sucedido não prova que a operação teve efeito. 75 das 78 receitas
documentadas em `docs/PLAYBOOK.md` foram reproduzidas ao vivo, com o resultado registrado em
`VERIFIED.json`; as outras 3 são globais/destrutivas demais para testar em automação
(`empty trash`, `log completed now`, `show quick entry panel`) e ficam documentadas como tal.

## Quando usar esta skill

Para qualquer operação em Things 3 que caiba num dos comandos abaixo. Para o que o CLI não cobre
(ex.: editar um checklist-item existente, endereçar um heading, ler recorrência), consulte
`docs/PLAYBOOK.md` — cada célula da matriz de capacidades tem o comando exato por trás, e o que é
`❌` ali é impossível de verdade, não falta de cobertura do CLI.

## Setup

```bash
pip install -e '.[dev]'          # uma vez, a partir de um clone deste repo
python3 -m things3.cli doctor    # roda antes de qualquer automação
```

`doctor` diagnostica a causa mais provável de qualquer coisa que pareça não funcionar: permissão de
automação nunca concedida, Things nunca aberto, token num arquivo que o shell não-interativo não lê.
Rodar sempre que uma operação falhar de um jeito que não faz sentido, antes de investigar mais.

## Comandos

Nenhum comando abaixo precisa de `--apply` exceto `checklist` e `delete` — os únicos onde algo pode
ser perdido. Os demais escrevem direto, porque nada que fazem é destrutivo no sentido de dado
perdido (criar, renomear, mover e trocar status são sempre reversíveis).

```bash
things3 create <todo|project|area|tag> "Título"
things3 rename <kind> <uuid> "Novo título"              # --by-name se o identificador for título
things3 move <uuid> --to-list Today                     # ou --to-project / --to-area
things3 status <kind> <uuid> <open|completed|canceled>
things3 restore <kind> <uuid>                            # só to-do e projeto voltam da Lixeira
things3 delete <kind> <uuid> --apply                     # Lixeira nativa e reversível para to-do/projeto
things3 delete area "Nome" --by-name --apply --allow-irreversible   # área/tag: irreversível, exige o flag extra
things3 checklist <uuid> --rename "Old=New" --apply       # única forma de editar item de checklist existente
things3 show <uuid>                                       # item + checklist + recorrência, tudo junto
```

`<kind>` é sempre um de `todo`, `project`, `area`, `tag`, `heading` (nem todo comando aceita todos —
`create` não aceita `heading`, por exemplo; o próprio CLI recusa com uma mensagem clara).

## O que o CLI não cobre

- **Editar um checklist-item que já existe** (renomear, marcar como feito, mover entre to-dos): não
  há comando dedicado porque a operação por baixo já é `checklist` — use-o.
- **Ler headings, checklist-items ou recorrência isoladamente** sem o `show`: importe
  `things3.read` diretamente (`read.headings(conn)`, `read.checklist_items(conn, uuid)`,
  `read.recurrence(conn, uuid)`).
- **Criar um heading**: só existe junto da criação do projeto —
  `things3.urlscheme.create_project_with_headings(titulo, [headings])`.
- **Recorrência (criar ou editar)**: impossível por qualquer via, incluindo composição. Só pela UI
  do próprio Things.

Para qualquer um desses, ou para qualquer dúvida sobre o que uma operação realmente faz, consultar
`docs/PLAYBOOK.md` antes de escrever AppleScript ou URL scheme à mão — ele tem o comando exato,
testado, para cada tipo × ação, e as armadilhas documentadas (`CONTRIBUTING.md` tem a lista
condensada das mais caras de descobrir sozinho).

## Regras importantes

- **Nunca inventar dados.** Só usar título, notas, prazos etc. que o usuário forneceu.
- **Usar só recursos nativos do Things.** Nunca criar estrutura própria (projeto/tag/área de
  controle) para contornar alguma limitação.
- **Exclusão é assimétrica por tipo** — já embutido no `delete` do CLI, mas importa saber: to-do e
  projeto vão para a Lixeira nativa e voltam com `restore`; área e tag são apagados de vez, exigem
  `--allow-irreversible` e o CLI grava backup automaticamente antes.
- **Nunca chamar `empty trash`.** Não existe comando no CLI para isso — de propósito.
- **`THINGS_AUTH_TOKEN`** só é necessário para `checklist --apply` (editar item existente). Nunca
  pedir para o usuário colar o token na conversa; se não estiver no ambiente, apontar para
  `Things → Configurações → Geral → Ativar Things URLs → Manage` e pedir para exportar numa sessão
  não-interativa (`~/.zshenv`, não `~/.zshrc` — `doctor` avisa exatamente isso se detectar o erro).
- **Coisas que a plataforma faz de propósito e não são bug**, para não gastar tempo investigando:
  um heading nunca recebe `trashed=1` mesmo com o projeto-pai na Lixeira (fica invisível, mas o
  registro persiste até o usuário esvaziar a lixeira manualmente); uma execução longa e sem pausa
  pode falhar transitoriamente sob carga, mesmo quando a operação isolada funciona sempre — ver
  "Verified limits" no `README.md`.
