# Regras fixas do PB Minuto

Valem para tudo o que o sistema produz. Cada regra tem um teste que falha se ela for quebrada.

## 1. Letra: só Inter
- Capa, vídeo, legenda do vídeo, logo, avatar e qualquer arte nova usam **só a Inter** (Inter e
  Inter Display, arquivos em `fonts/`). Destaque é peso, tamanho ou caixa, nunca outra família.
- Exceção: os ícones (`MaterialIcons`), que são desenhos, não letras.
- Onde mexer: `layout.py` (`FONTE`, `FONTE_DISPLAY`, `FONTE_LOGO`, `PAPEIS`).
- Teste: `tests/test_regra_fonte.py`.

## 2. Texto: skill STE80 Humanizer em toda escrita e reescrita
- A skill fica em `skills/ste80-humanizer/` (MIT). Atualizar o `SKILL.md` atualiza a regra.
- Na escrita: o prompt do editor (`editor.SYSTEM`) e o do revisor de originalidade
  (`editor.REESCRITOR`) trazem a REGRA DE ESCRITA da skill: uma ideia por frase, frases curtas, voz
  ativa, palavras simples, sem marcas de texto de IA (travessão, "não é só X, é Y", palavras infladas,
  gerúndio pendurado...).
- Depois da escrita: toda notícia, inclusive pauta pedida, "refazer" e os vídeos do parceiro
  (`parceiro.escrever`), passa por `editor.humanizar`,
  que revisa manchete, linha fina, resumo, tópicos e legenda. A narração é montada desses campos, então
  o áudio sai revisado junto.
- Fidelidade: se a revisão perder ou inventar número, estourar a manchete ou ficar parecida com a
  fonte, fica o texto original (a notícia sai do mesmo jeito).
- Só desligar em emergência: variável `HUMANIZAR=0` no GitHub.
- Teste: `tests/test_humanizar.py`.

## 3. Visual: editoria só em texto (pedido do Arthur, 21/11/2026)
- Na capa e nos Reels a editoria vai só como texto branco em CAIXA ALTA, sem o quadrado colorido do
  tema (`layout.EDITORIA_CAIXA = False`). As cores de `COR_EDITORIA` ficam guardadas, sem uso.

## 4. Vídeos dos parceiros autorizados (padrão desde 21/11/2026)
- Parceiros: @jornaldapb, @paraibabussines_, @portalresumopb, @noticiacertapb e @blognewspb
  (`parceiro.LISTA_PADRAO` ou a variável `PARCEIRO_LISTA`). Só entram Reels publicados depois da data
  em que cada perfil entrou na lista.
- @blognewspb e @portalresumopb usam moldura ("grade") com a marca deles: o sistema grava só a parte
  do vídeo que mexe.
- Só vídeos que NÃO são collab (a autorização cobre só esses).
- Verifica o Instagram de cada um a cada 15 min (agendamento do `parceiro.yml` + vigia no `publicar.yml`).
- Sem link pela API, baixa o Reel pela página do post (yt-dlp). Se o Instagram pedir login, salvar os
  cookies de uma conta secundária no segredo `PARCEIRO_IG_COOKIES`.
- Layout no vídeo e na capa do Reels: barra do PB Minuto, degradê preto que esconde a manchete antiga,
  etiqueta nova e desfoque automático da marca d'água/texto parado (`PARCEIRO_AUTO_MARCA=0` desliga).
- Publica direto, sem aprovação (`PARCEIRO_MODO=review` volta à fila de aprovação).
