# PB Minuto — portal de notícias automático no Instagram

Bot que roda sozinho no GitHub Actions, de hora em hora das 06h às 23h:

```
Google News (CG, JP, PB) + RSS dos portais e prefeituras
  -> agrupa as manchetes por assunto e exige 2 fontes (ou 1 fonte grande/oficial)
  -> só notícia local (Campina Grande, João Pessoa, Paraíba)
  -> IA editora escreve no padrão dos grandes portais (chapéu, título no presente, linha fina,
     lide, formatos "O que se sabe" / "Entenda" / "Veja como fazer", legenda)
  -> agente reescritor compara com as manchetes originais e reescreve até não sobrar
     nenhuma sequência de 4 palavras igual (se não conseguir, a notícia é descartada)
  -> filtro de temas sensíveis (suicídio, crime sexual, menores, acusação sem prova = não publica)
  -> a IA avalia as 3 melhores notícias da rodada pelo potencial de compartilhamento
     (utilidade, identificação, emoção, debate, status) e escolhe a mais forte
  -> desenha a capa 1080x1350 (foto do tema + manchete); os detalhes vão na legenda
  -> publica pela API oficial do Instagram
  -> grava no histórico para nunca repetir a notícia
     (por palavras e também por SENTIDO: embeddings do Gemini barram o mesmo fato escrito de outro jeito)
  -> 24h depois lê alcance, salvamentos e compartilhamentos de cada post e passa a
     priorizar as editorias e gatilhos que mais engajam (aprende sozinho)
```

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
| `POSTS_PER_RUN` | `1` | posts por execução (1 por hora) |
| `MAX_POSTS_PER_DAY` | `14` | teto diário |
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
3. Pronto: a partir daí ele publica sozinho de hora em hora.

Se uma publicação falhar (ex.: token vencido), a execução fica vermelha e o GitHub
manda e-mail.

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
