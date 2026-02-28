# Guia de Setup - Sistema de Monitoramento

## Passo 1: Configurar URLs dos Clones

Edite o arquivo [monitor/config/deployment_urls.json](config/deployment_urls.json):

```json
{
  "environments": [
    {
      "name": "production",
      "url": "https://ia-de-conversacao.vercel.app",
      "enabled": true,
      "priority": "critical"
    },
    {
      "name": "clone1",
      "url": "https://SEU_CLONE_1_URL_AQUI.vercel.app",
      "enabled": true,
      "priority": "high"
    },
    {
      "name": "clone2",
      "url": "https://SEU_CLONE_2_URL_AQUI.vercel.app",
      "enabled": true,
      "priority": "high"
    }
  ]
}
```

**Importante:** Substitua `SEU_CLONE_X_URL_AQUI` pelos URLs reais dos seus clones!

## Passo 2: Configurar Senha

O monitor precisa de uma senha para autenticar. Você tem 2 opções:

### Opção A: Variável de Ambiente do Sistema (Recomendado)

Abra PowerShell como Administrador e execute:

```powershell
[System.Environment]::SetEnvironmentVariable("MONITOR_PASSWORD", "<SENHA_FORTE_ADMIN>", "User")
```

**Ou via CMD:**

```batch
setx MONITOR_PASSWORD "<SENHA_FORTE_ADMIN>"
```

**Nota:** Substitua `<SENHA_FORTE_ADMIN>` pela senha real do admin.

### Opção B: Usar Senha Existente do .env

Se você já tem o arquivo `.env` com `ADMIN_PASSWORD`, o monitor usará automaticamente.

## Passo 3: Teste Manual (IMPORTANTE!)

Antes de configurar o agendamento automático, teste manualmente:

### 3.1 Abra PowerShell ou CMD

```batch
cd "C:\Users\whesl\OneDrive\Documentos\Projetos\_Projetos_Ativos\IA de conversação"
```

### 3.2 Ative o ambiente virtual

```batch
.venv\Scripts\activate
```

### 3.3 Execute o monitor

```batch
python monitor\monitor_app.py --env production
```

### 3.4 Verifique o resultado

- **Exit code 0**: ✅ Todos os testes passaram
- **Exit code 1**: ⚠️ Alguns testes falharam (warnings)
- **Exit code 2**: 🔴 Falha crítica

Verifique o relatório gerado:

```
monitor\reports\latest\summary.json
```

## Passo 4: Configurar Task Scheduler (Execução Automática)

Se o teste manual funcionou, configure para rodar de hora em hora:

### 4.1 Abrir Task Scheduler

1. Pressione `Win + R`
2. Digite `taskschd.msc`
3. Pressione Enter

### 4.2 Criar Nova Tarefa

1. Clique em **"Criar Tarefa"** (não "Criar Tarefa Básica")

### 4.3 Aba "Geral"

- **Nome:** MonitorEnglishApp
- **Descrição:** Sistema de monitoramento automático para IA de Conversação
- **Configurações de segurança:**
  - ✅ Executar estando o usuário conectado ou não (requer senha)
  - ⚪ Executar com privilégios mais altos (não necessário)

### 4.4 Aba "Disparadores"

1. Clique em **"Novo..."**
2. Configure:
   - **Iniciar a tarefa:** Em uma agenda
   - **Configurações:** Diariamente
   - **Iniciar:** (data/hora de hoje)
   - **Recorrer a cada:** 1 dias
   - ✅ **Repetir tarefa a cada:** 1 hora
   - **Por um período de:** Indefinidamente
   - ✅ **Habilitado**
3. Clique em **OK**

### 4.5 Aba "Ações"

1. Clique em **"Novo..."**
2. Configure:
   - **Ação:** Iniciar um programa
   - **Programa/script:** `C:\Users\whesl\OneDrive\Documentos\Projetos\_Projetos_Ativos\IA de conversação\MONITOR.bat`
   - **Iniciar em (opcional):** `C:\Users\whesl\OneDrive\Documentos\Projetos\_Projetos_Ativos\IA de conversação`
3. Clique em **OK**

### 4.6 Aba "Condições"

- ✅ **Acordar o computador para executar esta tarefa**
- ⚪ Iniciar a tarefa apenas se o computador estiver em energia CA (desmarcar se for laptop)

### 4.7 Aba "Configurações"

- ✅ **Permitir que a tarefa seja executada por solicitação**
- ✅ **Executar tarefa assim que possível após uma inicialização agendada ter sido perdida**
- ✅ **Se a tarefa falhar, reiniciar a cada:** 10 minutos
- **Tentar reiniciar até:** 3 vezes
- **Parar a tarefa se ela for executada por mais de:** 1 hora
- ✅ **Se a tarefa em execução não terminar quando solicitado, forçar sua interrupção**

### 4.8 Salvar

1. Clique em **OK**
2. Digite sua senha do Windows se solicitado

## Passo 5: Testar Tarefa Agendada

1. No Task Scheduler, encontre **MonitorEnglishApp**
2. Clique com botão direito → **Executar**
3. Aguarde finalizar
4. Verifique se `monitor_success.log` foi atualizado

## Verificar Resultados

### Logs de Execução

- **Sucessos:** `monitor_success.log`
- **Warnings:** `monitor_warnings.log`
- **Erros críticos:** `monitor_errors.log`

### Relatórios Detalhados

```
monitor\reports\latest\summary.json
monitor\reports\latest\monitor.log
```

## Troubleshooting

### "No module named 'monitor'"

Certifique-se de executar a partir do diretório raiz do projeto.

### "No password found in environment variable"

Execute novamente o Passo 2 para configurar a senha.

### "Authentication failed"

Verifique se o email e senha em `deployment_urls.json` estão corretos.

### Task Scheduler não executa

- Verifique se o caminho do MONITOR.bat está correto
- Teste executar o MONITOR.bat manualmente primeiro
- Verifique logs do Task Scheduler (visualizar histórico)

### Relatório não abre automaticamente

Normal se não houver falhas críticas. Para falhas críticas (exit code 2), o HTML deveria abrir automaticamente.

## Próximos Passos

O sistema atual testa todos os **endpoints da API**. Para adicionar mais testes:

1. **Cenários de conversação**: Implemente `test_suite_scenarios.py`
2. **Tópicos gramaticais**: Implemente `test_suite_grammar.py`
3. **Áudio (TTS/STT)**: Implemente `test_suite_audio.py`
4. **Testes E2E**: Implemente `test_suite_e2e.py`

Use `test_suite_endpoints.py` como template.

## Comandos Úteis

```batch
# Testar apenas production
python monitor\monitor_app.py --env production

# Testar todos os ambientes
python monitor\monitor_app.py --all-envs

# Executar via launcher
MONITOR.bat

# Gerar amostras de áudio (para testes futuros)
python monitor\utils\audio_generator.py --generate-samples
```

## Suporte

Documentação completa em: [monitor/README.md](README.md)
