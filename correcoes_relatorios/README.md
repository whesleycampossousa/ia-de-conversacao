# Correções Diárias Everyday Conversation

Esta pasta contém o núcleo versionado do fluxo de correções com HTML premium, áudios Clone 16, áudios reais dos alunos e validações pedagógicas.

## O que está no GitHub

- `generate_multiatividades_clone16_audio_report.py`: motor base do relatório.
- `generate_base_clone16_audio_report.py`: camada visual/pedagógica usada nos relatórios recentes.
- `correction_quality_guardrails.py`: validações contra erros recorrentes.
- `PROMPT_CORRECOES_RELATORIOS.md`: contrato pedagógico das correções.
- `visual_reference.css` e `assets_relatorios/`: padrão visual.
- `build_data_template.py` e `generate_daily_report_template.py`: templates para criar o dia novo.

## O que fica fora do GitHub

- Áudios dos alunos.
- Prints do WhatsApp.
- HTMLs publicados.
- Cache de TTS/áudios gerados.
- Voz de referência Clone 16, caso esteja em pasta privada.

## Setup em outro laptop

1. Clonar o repositório.
2. Instalar Python e dependências:

```powershell
pip install -r correcoes_relatorios\requirements.txt
```

3. Instalar/ter disponíveis:

- FFmpeg no `PATH`.
- Tesseract, se for usar OCR.
- Netlify CLI, se for publicar: `npm install -g netlify-cli`.
- A voz de referência Clone 16 no laptop.

4. Se a voz de referência não estiver no caminho padrão, apontar:

```powershell
$env:EC_CLONE16_REF_AUDIO="C:\caminho\para\reference_22s.wav"
```

## Como criar um relatório novo

1. Copiar os templates:

```powershell
Copy-Item correcoes_relatorios\build_data_template.py correcoes_relatorios\build_data_12_junho.py
Copy-Item correcoes_relatorios\generate_daily_report_template.py correcoes_relatorios\generate_12_junho_clone16_audio_report.py
```

2. Editar:

- `build_data_12_junho.py`: colocar as correções em `ROWS`.
- `generate_12_junho_clone16_audio_report.py`: colocar `REPORT_SLUG`, `INPUT_DIR`, atividades, data e `STRICT_AUDIO_MAP`.

3. Rodar:

```powershell
python correcoes_relatorios\build_data_12_junho.py
python correcoes_relatorios\generate_12_junho_clone16_audio_report.py
```

4. Validar o HTML local antes de publicar.

## Regra crítica

Não trocar palavra correta do aluno por sinônimo e destacar como erro. Se o aluno escreveu `kid`, `love`, `fine`, `so good`, etc. e está correto, preserve. Se a troca for uma sugestão estilística excepcional, a observação precisa dizer claramente que a forma original também estava correta.
