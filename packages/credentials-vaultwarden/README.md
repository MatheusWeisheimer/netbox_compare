# netbox-compare-vaultwarden

Módulo de credenciais do netbox-compare para [Vaultwarden](https://github.com/dani-garcia/vaultwarden) (e Bitwarden). Busca o usuário e a senha de cada equipamento no cofre.

Entry point: `vaultwarden` (grupo `netbox_compare.credentials`).

## Como funciona

- O equipamento é associado ao item do tipo **Login** cujo nome é **igual ao nome do equipamento** no NetBox.
- O host da conexão é o **IP primário** do equipamento no NetBox. A URL do item não é usada.
- Se houver dois itens com o mesmo nome, o equipamento não é comparado (credencial ambígua).
- O cofre é descriptografado localmente. Os segredos ficam apenas na memória do processo, em um cache de 5 minutos (`cache_ttl`).

## Instalação

No venv do NetBox, junto com o core:

```bash
sudo /opt/netbox/venv/bin/pip install ./packages/core ./packages/credentials-vaultwarden
```

## Preparação no Vaultwarden

1. Crie uma conta dedicada ao netbox-compare (ou uma organização compartilhada com ela) com os itens Login dos equipamentos.
2. Preencha usuário e senha em cada item. Itens sem um dos dois são ignorados.
3. Gere a chave de API da conta: cofre web → Configurações da conta → Segurança → Chaves → Ver chave de API. Anote `client_id` e `client_secret`.

## Configuração

```python
import os

"credentials": [
    {
        "module": "vaultwarden",
        "config": {
            "url": "https://vault.exemplo.com.br",
            "client_id": os.environ.get("NBC_VW_CLIENT_ID", ""),
            "client_secret": os.environ.get("NBC_VW_CLIENT_SECRET", ""),
            "email": os.environ.get("NBC_VW_EMAIL", ""),
            "master_password": os.environ.get("NBC_VW_MASTER_PASSWORD", ""),
        },
    },
],
```

| Chave | Obrigatória | Descrição |
|---|---|---|
| `url` | sim | URL do Vaultwarden |
| `client_id`, `client_secret` | sim | Chave de API da conta |
| `email`, `master_password` | sim | Necessários para descriptografar o cofre |
| `verify` | não | Verificação TLS: `True` (padrão), `False` ou caminho de um certificado de CA |
| `timeout` | não | Segundos por requisição HTTP, padrão 10 |
| `cache_ttl` | não | Segundos em que o cofre descriptografado é reutilizado, padrão 300 |
| `failure_backoff` | não | Segundos de espera antes de tentar de novo após uma falha, padrão 30 |
| `device_id` | não | Identificador de dispositivo Bitwarden (padrão: derivado de `url` e `client_id`) |

Mantenha os segredos fora do `configuration.py`, em variáveis de ambiente lidas pelo NetBox e pelo `rqworker`.

## Testes

```bash
uv run pytest packages/credentials-vaultwarden
```

Testes contra um Vaultwarden real (variáveis `NBC_VW_*`, descritas em [`.env.example`](.env.example), que devem estar no `.env` da raiz; `NBC_VW_TEST_ITEM` é o nome de um item Login existente):

```bash
set -a; . ./.env; set +a; uv run pytest -m live packages/credentials-vaultwarden
```
