# Especificações

Status: aguardando detalhamento.

## Definido

- Nome: `laya-dataset-manager`.
- Ambiente: Ubuntu no WSL2.
- Execução: Docker e Docker Compose.
- Versionamento: repositório público no GitHub.
- Laya: implementação oficial Python/PyTorch `NandhaKishorM/laya`, versão 0.3.11.
- Hardware detectado: NVIDIA RTX 2000 Ada, 8 GB de VRAM.
- Runtime inicial: PyTorch 2.11.0 com CUDA 12.8, checkpoint multilíngue e API local na porta 8000.
- Cache dos modelos: volume Docker fora do Git.

## A definir

- Objetivo funcional e integração do gerenciador com a API do Laya.
- Usuários e fluxo de trabalho.
- Formatos, importação, organização e validação dos datasets.
- Estratégia de treinamento/fine-tuning. A interface oficial de treinamento do Laya ainda não está estabilizada; o container atual fornece inferência.
- Interface, backend e persistência.
- Critérios de aceite.
