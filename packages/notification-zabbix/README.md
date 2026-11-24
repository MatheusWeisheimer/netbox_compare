# netbox-compare-zabbix

Módulo de notificação do netbox-compare para [Zabbix](https://www.zabbix.com/). Ao fim de cada execução agendada, envia o resultado de cada equipamento para itens *trapper* do host Zabbix com o mesmo nome.

Entry point: `zabbix` (grupo `netbox_compare.notifications`).

## Itens enviados

O template [`contrib/zabbix_template.yaml`](../../contrib/zabbix_template.yaml) ("netbox-compare drift") define os itens e as triggers:

| Item | Valor |
|---|---|
| `netbox.compare.severity` | Maior severidade das divergências: 0 (nenhuma) a 4 (crítica). Há uma trigger por nível. |
| `netbox.compare.divergences` | Número de divergências |
| `netbox.compare.status` | 0 comparado, 1 não foi possível comparar |
| `netbox.compare.report` | Resumo em texto |

Uma execução sem divergências envia severidade 0 e o problema é resolvido. Uma comparação que falhou envia só `status` e `report`. Equipamentos pulados por falta de configuração (sem módulo de conexão ou sem credenciais) não enviam nada.

## Instalação

No venv do NetBox, junto com o core:

```bash
sudo /opt/netbox/venv/bin/pip install ./packages/core ./packages/notification-zabbix
```

## Preparação no Zabbix

Requer Zabbix 7.0 ou superior para o transporte `api`.

1. Importe `contrib/zabbix_template.yaml` (Data collection → Templates → Import).
2. Vincule o template "netbox-compare drift" aos hosts dos equipamentos. O nome do host deve ser igual ao nome do equipamento no NetBox, ou mapeado em `hosts`.
3. Para o transporte `api`: crie um token de API (Users → API tokens) de um usuário com acesso a esses hosts.

## Configuração

```python
import os

"notifications": [
    {
        "module": "zabbix",
        "config": {
            "url": "https://zabbix.exemplo.com.br",
            "token": os.environ["NBC_ZBX_TOKEN"],
        },
    },
],
```

Depois, selecione o módulo `zabbix` nos agendamentos que devem notificar.

| Chave | Padrão | Descrição |
|---|---|---|
| `transport` | `"api"` | `"api"` (`history.push`, Zabbix 7.0+) ou `"trapper"` (protocolo do zabbix_sender) |
| `url` | | API: URL do frontend ou o `.../api_jsonrpc.php` completo |
| `token` | | API: token de API |
| `verify` | `True` | API: verificação TLS, `True`, `False` ou caminho de um certificado de CA |
| `server` | | Trapper: endereço do Zabbix server ou proxy |
| `port` | `10051` | Trapper: porta |
| `timeout` | `10` | Segundos |
| `item_prefix` | `"netbox.compare"` | Prefixo das chaves dos itens (deve bater com o template) |
| `hosts` | `{}` | `{nome do equipamento no NetBox: nome do host no Zabbix}`, para nomes diferentes |

O transporte `api` informa quais valores foram rejeitados; o `trapper` só informa quantos. Prefira `api`.

## Testes

```bash
uv run pytest packages/notification-zabbix
```

Testes contra um Zabbix real (variáveis `NBC_ZBX_*`, descritas em [`.env.example`](.env.example), que devem estar no `.env` da raiz; `NBC_ZBX_TEST_HOST` é um host vinculado ao template e `NBC_ZBX_TRAPPER` opcionalmente testa o transporte trapper):

```bash
set -a; . ./.env; set +a; uv run pytest -m live packages/notification-zabbix
```
