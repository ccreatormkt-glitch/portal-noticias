# PB Minuto — portal de notícias automático no Instagram

Bot que roda sozinho no GitHub Actions, 24 horas por dia, 7 dias por semana. Confere notícia nova a
cada ~5 minutos e vídeos/posts dos parceiros a cada ~20; publica 1 Reels a cada ~14 min (até 95
publicações em 24h, Stories incluídos; a API do Instagram aceita 100):

```
Google News + 55 RSS da Paraíba (portais, órgãos, prefeituras) + Brasil + Mundo
  -> agrupa as manchetes por assunto; 1 fonte basta (crime/acusação de site pequeno pede 2)
  -> mix de audiência: Campina Grande 30%, João Pessoa 20%, Brasil 30%, Mundo 20%
     (interior conta para CG, litoral para JP; no máximo 2 seguidas da mesma categoria)
  -> IA editora escreve no padrão dos grandes portais (chapéu, título no presente, linha fina,
     lide, legenda) e o reescritor tira qualquer sequência de 4 palavras igual às fontes
  -> filtro de temas sensíveis (suicídio, crime sexual, menores, acusação sem prova = não publica)
  -> Reels 2K: capa (foto + manchete) e vídeo com narração em voz de IA, onda de áudio e legenda
     palavra por palavra; a narração termina sempre com "Siga o PB Minuto."
  -> publica pela API oficial do Instagram; posts da Paraíba também vão para os Stories
  -> alterna com os parceiros: sem vídeo de parceiro na vez dele, sai notícia (nunca fica parado)
  -> grava no histórico para nunca repetir a notícia
     (por palavras e também por SENTIDO: embeddings do Gemini barram o mesmo fato escrito de outro jeito)
  -> 24h depois lê alcance, salvamentos e compartilhamentos e prioriza o que mais engaja
```

As regras de conteúdo e publicação estão em `REGRAS.md` (hashtags minúsculas, mix, Stories,
parceiros, encerramento "Siga o PB Minuto" etc.).

Nada é copiado: o texto é reescrito e a arte é própria. As fontes não aparecem no post,
mas ficam gravadas em `state/log.jsonl` (cada notícia publicada e de onde veio), para conferência.

## Configuração (uma vez)

No repositório: **Settings > Secrets and variables > Actions**.

**Secrets** (ficam criptografados):

| Nome | O que é |
|---|---|
| `GEMINI_API_KEY` | chave grátis em aistudio.google.com/apikey |
| `IG_USER_ID` | ID da conta do Instagram (Comercial/Criador) |
| `IG_ACCESS_TOKEN` | token de acesso de longa duração da Meta |
| `IMGBB_API_KEY` | chave grátis em api.imgbb.com |
| `PEXELS_API_KEY` | chave grátis em pexels.com/api (fotos do tema) |

**Variables** (opcionais):

| Nome | Padrão | Para que serve |
|---|---|---|
| `POST_MODE` | `auto` | `auto` publica sozinho; `review` deixa na fila |
| `MAX_POSTS_PER_DAY` | `95` | teto de publicações em 24h (Stories contam) |
| `INTERVALO_POSTS_MIN` | ~14 | minutos entre publicações (calculado do teto) |
| `MIX` | `cg:30,jp:20,brasil:30,mundo:20` | divisão das publicações por categoria |
| `STORIES` | `paraiba` | `paraiba`, `todos` ou `nenhum` |
| `SENSITIVE_MODE` | `careful` | `careful` publica polícia com cuidado; `skip` não publica |
| `IMAGE_MODE` | `none` | `gemini` gera ilustração de fundo por IA quando não há foto |
| `CAROUSEL` | `false` | `true` adiciona a lâmina de detalhes (carrossel) |
| `PORTAL_NAME` / `PORTAL_HANDLE` | PB Minuto / @pbminuto | marca nos cards |
| `VIDEO_FUNDO` | `true` | fundo do Reels com trecho de vídeo do Pixabay (a foto fica de reserva); `false` = só foto |
| `SEMANTICO` | `true` | trava anti-repetição por sentido (embeddings) |
| `SIMILARIDADE_MAX` | `0.90` | de 0 a 1: acima disto é o mesmo fato; baixe se ainda escapar repetida, suba se barrar notícia nova |

## Primeiros passos

1. Aba **Actions > checar-configuracao > Run workflow**: testa IA, Instagram, hospedagem e fontes.
2. **Actions > publicar-noticias > Run workflow** com modo `dry`: gera 3 cards de teste
   (baixe em "Artifacts > cards") sem publicar nada.
3. Pronto: a partir daí ele publica sozinho, 24h por dia.

Se uma publicação falhar (ex.: token vencido), a execução fica vermelha e o GitHub
manda e-mail.

## Parceiros (vídeos e posts de imagem)

Perfis que autorizaram o uso do conteúdo (`LISTA_PADRAO` em `parceiro.py`, workflow
**parceiro-jornaldapb**, a cada 20 min). Hoje: @jornaldapb, @paraibabussines_, @portalresumopb,
@noticiacertapb (vídeos e carrosséis de notícia), @blognewspb, @bombaparaiba_ (só imagens) e @destaques.dodia (vídeos e imagens).
Só entram posts publicados depois da data de cada parceiro, e nunca collab/publi.

- lê os posts pela API oficial (Business Discovery, mesmo token do portal);
- vídeo: baixa, transcreve a fala, tira a marca d'água do próprio parceiro (flags `faixa`, `marca`,
  `grade`), escolhe o melhor quadro para a capa e põe a nossa barra com logo e editoria;
- imagem (flag `imagem`): recorta a foto central da moldura e monta um Reels do PB Minuto;
- a IA reescreve editoria, manchete e legenda pela regra das notícias e confere a fidelidade;
  dúvida vai para a fila (Run workflow → aprovar);
- publica direto (`PARCEIRO_MODO=auto`) e, se for da Paraíba, também nos Stories;
- marca de terceiros (agência, fotógrafo, outro perfil) nunca é removida.

Para incluir um parceiro: skill `pb-minuto-novo-parceiro` (ações `amostra`, `calibrar-marca`,
`teste-parceiro`, `teste-imagem`). Para ver/aprovar a fila: skill `pb-minuto-aprovar-parceiro`.

| Variável | Padrão | Para que serve |
|---|---|---|
| `PARCEIRO_MODO` | `auto` | `review` deixa tudo na fila de aprovação |
| `PARCEIRO_LISTA` | lista do código | `perfil|desde|flags; ...` para trocar a lista sem mexer no código |
| `PARCEIRO_JANELA_HORAS` | `48` | ignora posts mais velhos que isso |

Prévias (quadros, capas e vídeos de teste) ficam no ramo `previa-parceiro`.

## Outros workflows

| Workflow | Para que serve |
|---|---|
| `boletim-bom-dia` | Reels "Bom dia, Paraíba" às 6h40 (tempo e destaques) |
| `apagar-post` | apaga um post pelo texto ou id (só com `confirmar`) |
| `corrigir-noticia` | correção pública de uma notícia publicada |
| `aprovar-fila` | publica o que está na fila de revisão |
| `testar-fontes` | testa se os sites/RSS de notícia respondem |
| `testes` | roda os testes automáticos |

## Comandos locais

```bash
pip install -r requirements.txt
python main.py demo            # cards de exemplo, sem chave
python main.py check-feeds     # quais fontes estão respondendo
python main.py run --dry-run   # ciclo completo sem publicar (cards em out/)
python main.py run             # ciclo real
```

Para mudar fontes, edite `FEEDS` em `sources.py`. Para mudar o estilo do texto,
edite `SYSTEM` em `editor.py`. Para mudar o visual, `render.py`.

Arquitetura inspirada no projeto aberto `mekalabhagy/telugu-news-bot`.
Fonte Inter (SIL Open Font License).
