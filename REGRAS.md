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
- Depois da escrita: toda notícia, inclusive pauta pedida e "refazer", passa por `editor.humanizar`,
  que revisa manchete, linha fina, resumo, tópicos e legenda. A narração é montada desses campos, então
  o áudio sai revisado junto.
- Fidelidade: se a revisão perder ou inventar número, estourar a manchete ou ficar parecida com a
  fonte, fica o texto original (a notícia sai do mesmo jeito).
- Só desligar em emergência: variável `HUMANIZAR=0` no GitHub.
- Teste: `tests/test_humanizar.py`.
