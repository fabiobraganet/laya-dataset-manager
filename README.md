# Laya Dataset Manager

Aplicação para gerenciamento de datasets e apoio ao treinamento do Laya.

## Estado atual

Estrutura inicial de infraestrutura, com uma página provisória servida pelo Nginx e endpoint `/health`. As funcionalidades, a stack da aplicação, o armazenamento e os requisitos de treinamento serão definidos na próxima etapa. Nenhum treinamento é executado nesta base.

## Ambiente

- Ubuntu no WSL2 (distribuição `Ubuntu`).
- Docker Engine e Docker Compose disponíveis dentro do Ubuntu.
- Projeto local em `/opt/projects/laya-dataset-manager`.

No PowerShell, entre no projeto:

```powershell
wsl -d Ubuntu --cd /opt/projects/laya-dataset-manager
```

No Ubuntu:

```bash
cp .env.example .env
docker compose up -d --build --wait
```

Acesse <http://localhost:8080>. A porta é publicada somente no endereço local. Para alterar a porta, ajuste `APP_PORT` no `.env`.

## Comandos

```bash
docker compose config --quiet
docker compose ps
curl --fail http://localhost:8080/health
docker compose logs -f
docker compose down
```

Após editar a página ou a configuração do Nginx, execute novamente `docker compose up -d --build --wait`.

## Organização

- `public/`: página provisória.
- `docker/`: configuração do container.
- `compose.yaml` e `Dockerfile`: ambiente reproduzível; imagem base fixada por digest.
- `docs/`: especificações do projeto.
- `data/`: reservado para arquivos locais, ignorados pelo Git.

O repositório é destinado a ser público. Datasets, modelos, checkpoints e segredos não devem ser versionados. O `.env.example` contém apenas configuração de exemplo. O serviço inicial não monta nem processa datasets.

## Próxima etapa

Detalhar o fluxo de trabalho, formatos de dataset, integração com Laya, requisitos de GPU e critérios de aceite em `docs/specifications.md`.
