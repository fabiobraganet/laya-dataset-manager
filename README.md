# Laya Dataset Manager

Aplicação local para criar, validar, versionar e treinar datasets tipados do [LAYA](https://github.com/NandhaKishorM/laya). O produto usa Rust/Axum, SQLite, Docker Compose, um executor Kaggle separado e o runtime LAYA com GPU.

## Fluxo suportado

1. Crie um dataset e inclua exemplos manualmente ou por JSONL.
2. Corrija os diagnósticos de schema, IDs duplicados, perguntas e respostas.
3. Congele uma `DatasetVersion` imutável. A versão registra quantidade, contrato e SHA-256.
4. Execute a pré-validação e envie a versão ao kernel privado do Kaggle.
5. Acompanhe status e logs reais; ao concluir, o executor baixa e valida o checkpoint.
6. Ative um artefato validado no runtime LAYA.
7. Execute inferências reais com `state` e `questions` pela tela **Modelos**.

## Serviços

| Serviço | Responsabilidade | Endereço local |
| --- | --- | --- |
| `web` | API Rust/Axum, SQLite e interface Tabler | <http://127.0.0.1:8080> |
| `laya` | Runtime LAYA e modelo especializado ativo | <http://127.0.0.1:8000> |
| `kaggle-executor` | Exportação, submissão, monitoramento e coleta | <http://127.0.0.1:8090> |

As portas são publicadas apenas em `127.0.0.1`. Dados, cache e modelos ficam em volumes Docker, fora do Git.

## Pré-requisitos

- WSL2 com a distribuição registrada como `Ubuntu`;
- Docker Engine com Docker Compose;
- GPU NVIDIA acessível pelo Docker para o runtime LAYA;
- conta Kaggle com acesso a notebooks e aceleradores;
- Git e GitHub CLI para contribuição.

## Configurar integrações

Depois de iniciar o aplicativo, abra **Configurações** na navegação principal.

- **Kaggle:** informe o API token atual ou, para contas antigas, usuário e chave. O aplicativo valida a conexão antes de salvar.
- **Hugging Face:** informe um access token. O runtime consulta a identidade da conta antes de salvar.

As credenciais são gravadas com acesso restrito nos volumes Docker locais `kaggle-run-state` e `laya-model-cache`. Elas não são armazenadas no SQLite, incluídas em imagens, retornadas pela API ou reapresentadas na interface. Para trocar uma credencial, salve a nova chave no mesmo formulário; a anterior é substituída somente depois que a nova conexão for validada.

## Iniciar

```bash
cd /opt/projects/laya-dataset-manager
docker compose -f compose.yaml -f compose.executor.yaml up -d --build
```

Confira os serviços:

```bash
docker compose -f compose.yaml -f compose.executor.yaml ps
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8090/health
```

Abra <http://127.0.0.1:8080>.

## Contrato JSONL

Cada linha é um objeto independente:

```json
{"id":"caso-001","state":{"claim":"Entrega comprovada no prazo."},"questions":{"decision":{"type":"choice","labels":["aprovar","rejeitar"]}},"gold":{"decision":"aprovar"}}
```

Tipos aceitos:

- `noul`: resposta booleana;
- `choice`: resposta presente em `labels` ou `choices`;
- `score`: critérios obrigatórios, valor entre 0 e 1 e probabilidades, quando presentes, somando 1.

A importação é incremental e registra arquivo, total, válidos, inválidos, duplicados e o diagnóstico de cada linha. A exportação de uma versão é determinística e ordenada por ID.

## Treinamento e artefatos

A interface envia exclusivamente uma `DatasetVersion`. O executor gera o JSONL e o notebook fixado, publica o kernel privado, acompanha o estado real e baixa os outputs. Um treinamento só fica `succeeded` após validar:

- manifesto e SHA-256;
- arquivo não vazio;
- estrutura SafeTensors;
- quantidade de tensores;
- presença do `model.safetensors` no diretório carregável.

O checkpoint é materializado no volume `laya-dataset-manager-model-artifacts`. A ativação somente é persistida no banco depois que o runtime consegue carregar o modelo como `typed-decisions`.

## Inferência

Na tela **Modelos**, ative um checkpoint validado e selecione **Testar inferência**. Informe `state` e `questions`; a resposta exibida vem de `POST /v1/systemone` do runtime LAYA.

A mesma operação pode ser testada pela API da aplicação:

```bash
curl --fail http://127.0.0.1:8080/api/inference \
  -H 'content-type: application/json' \
  --data '{"state":{"claim":"Entrega comprovada."},"questions":{"decision":{"type":"choice","labels":["aprovar","rejeitar"]}}}'
```

## Operação

```bash
docker compose -f compose.yaml -f compose.executor.yaml logs -f web
docker compose -f compose.yaml -f compose.executor.yaml logs -f kaggle-executor
docker compose -f compose.yaml -f compose.executor.yaml logs -f laya
docker compose -f compose.yaml -f compose.executor.yaml down
```

Volumes persistentes:

- `laya-dataset-manager-app-data`: banco SQLite;
- `laya-dataset-manager-model-cache`: cache do LAYA/Hugging Face;
- `laya-dataset-manager-model-artifacts`: checkpoints validados;
- `laya-dataset-manager_kaggle-run-state`: estado do executor.

## Desenvolvimento e verificação

```bash
docker compose -f compose.yaml -f compose.executor.yaml config --quiet
docker compose -f compose.yaml -f compose.executor.yaml build
docker compose -f compose.yaml -f compose.executor.yaml up -d
docker compose -f compose.yaml -f compose.executor.yaml ps
```

O build do serviço `web` executa os testes Rust. Antes de publicar alterações, teste no navegador criação/edição/remoção, importação, filtros, versões, pré-validação, execução, logs, modelos, ativação e inferência.

## Estrutura

- `src/`: domínio, API e persistência Rust;
- `static/`: interface Tabler, Bootstrap e CodeMirror;
- `training/executor/`: executor Kaggle isolado;
- `training/kaggle/`: utilitários de notebook;
- `docker/laya/`: runtime LAYA com ativação controlada;
- `compose.yaml` e `compose.executor.yaml`: serviços, volumes e healthchecks;
- `skills/github-workflow/`: processo de PR, revisão semântica e merge.

## Segurança

Não versione credenciais, datasets privados, checkpoints, outputs ou tokens. Os exemplos sintéticos incluídos para teste devem ser identificados como sintéticos e não representam dados de clientes. Use uma versão de avaliação separada antes de promover um modelo para uso real.
