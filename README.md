# netbox-compare

Detecta **desvio de configuração** entre o estado *documentado* no NetBox e o estado *observado* nos equipamentos de rede. Gera um relatório de divergências e deixa o administrador decidir, para cada uma, se corrige a documentação ou o equipamento.

## Pacotes

| Pacote | Diretório | Função |
|---|---|---|
| `netbox-compare` | [`packages/plugin`](packages/plugin) | Plugin do NetBox: modelos, telas, jobs, comparação e API REST |
| `netbox-compare-core` | [`packages/core`](packages/core) | Modelo canônico e contratos dos módulos (sem Django) |
| `netbox-compare-napalm` | [`packages/connection-napalm`](packages/connection-napalm) | Módulo de conexão: lê os equipamentos via NAPALM |
| `netbox-compare-vaultwarden` | [`packages/credentials-vaultwarden`](packages/credentials-vaultwarden) | Módulo de credenciais: busca usuário e senha no Vaultwarden |
| `netbox-compare-zabbix` | [`packages/notification-zabbix`](packages/notification-zabbix) | Módulo de notificação: envia o resultado dos jobs agendados ao Zabbix |

Os módulos são descobertos por *entry points*: basta instalar o pacote no mesmo ambiente do NetBox e configurá-lo em `PLUGINS_CONFIG`.

## Requisitos

- NetBox 4.5 ou superior, com o worker (`rqworker`) rodando
- Python 3.12 ou superior
- O servidor do NetBox precisa alcançar os equipamentos (SSH) e os serviços usados pelos módulos (Vaultwarden, Zabbix)

## Instalação

Os pacotes não estão publicados no PyPI. Eles são instalados a partir deste repositório, no venv do NetBox. Os exemplos usam a instalação padrão em `/opt/netbox`.

### 1. Obter o código

```bash
sudo git clone https://github.com/MatheusWeisheimer/netbox_compare.git /opt/netbox-compare
```

### 2. Instalar os pacotes no venv do NetBox

Instale todos no mesmo comando, para que o pip resolva `netbox-compare-core` a partir do diretório local:

```bash
cd /opt/netbox-compare
sudo /opt/netbox/venv/bin/pip install \
    ./packages/core \
    ./packages/plugin \
    "./packages/connection-napalm[vrp]" \
    ./packages/credentials-vaultwarden \
    ./packages/notification-zabbix
```

Instale só os módulos que for usar. O extra `[vrp]` instala o driver NAPALM para Huawei VRP.

Para que o `upgrade.sh` do NetBox reinstale os pacotes, adicione os mesmos caminhos em `/opt/netbox/local_requirements.txt`:

```text
/opt/netbox-compare/packages/core
/opt/netbox-compare/packages/plugin
/opt/netbox-compare/packages/connection-napalm[vrp]
/opt/netbox-compare/packages/credentials-vaultwarden
/opt/netbox-compare/packages/notification-zabbix
```

### 3. Configurar o NetBox

Em `/opt/netbox/netbox/netbox/configuration.py`:

```python
PLUGINS = ["netbox_compare"]

PLUGINS_CONFIG = {
    "netbox_compare": {
        "credentials": [
            {"module": "vaultwarden", "config": {...}},
        ],
        "connections": [
            {"module": "napalm", "config": {...}},
        ],
        "notifications": [
            {"module": "zabbix", "config": {...}},
        ],
        "os_version_custom_field": "os_version",
        "notification_deadline": 60,
        "base_url": "https://netbox.exemplo.com.br",
    },
}
```

O `config` de cada módulo está descrito no README do pacote. Não escreva segredos direto no arquivo: leia de variáveis de ambiente (`os.environ`). O arquivo [`contrib/netbox_configuration_snippet.py`](contrib/netbox_configuration_snippet.py) mostra um exemplo completo.

| Chave | Padrão | Descrição |
|---|---|---|
| `credentials` | `[]` | Módulos de credenciais, em ordem. Vale o primeiro que resolver o equipamento. |
| `connections` | `[]` | Módulos de conexão, em ordem. O equipamento usa o primeiro que declarar a sua *platform*. |
| `notifications` | `[]` | Módulos de notificação. Cada agendamento escolhe quais usar. |
| `os_version_custom_field` | `None` | Nome do *custom field* de Device com a versão do SO. Sem ele, a versão do SO fica "não comparável". |
| `notification_deadline` | `60` | Minutos após o início de uma execução agendada para finalizá-la e notificar, mesmo com comparações pendentes (que são marcadas como falhas). |
| `base_url` | `None` | URL externa do NetBox, usada nos links das notificações. |

### 4. Aplicar as migrações e reiniciar

```bash
cd /opt/netbox/netbox
sudo /opt/netbox/venv/bin/python manage.py migrate netbox_compare
sudo systemctl restart netbox netbox-rq
```

A migração cria uma política de comparação padrão.

### 5. Preparar os dados no NetBox

Para que um equipamento possa ser comparado, ele precisa ter:

- uma **platform** cujo *slug* esteja configurado em um módulo de conexão (ex.: `huawei-vrp`);
- um **IP primário**, que é o endereço usado para conectar;
- credenciais resolvíveis por um módulo de credenciais (no Vaultwarden: um item Login com o mesmo nome do equipamento).

Se usar `os_version_custom_field`, crie o *custom field* de texto em Device com esse nome.

### 6. Verificar

Abra um equipamento no NetBox e clique em "Compare with device running configuration". O job roda em segundo plano e o relatório aparece na aba "Device comparison results" do equipamento.

## Uso

- **Comparação manual**: botão na página do equipamento, com a política padrão ou outra escolhida.
- **Relatórios**: `/plugins/compare/comparisons/`. Para cada divergência o administrador escolhe corrigir a documentação, o equipamento ou nada.
- **Políticas**: definem quais campos são comparados e a severidade de cada um.
- **Agendamentos**: equipamentos e tags, política, horário, recorrência e módulos de notificação. Jobs agendados nunca aplicam correções.
- **API REST**: `/api/plugins/compare/` (`policies`, `schedules`, `runs`, `comparisons`).

## Desenvolvimento

Requer [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                            # ambiente com core e módulos
uv run pytest                                      # testes unitários
set -a; . ./.env; set +a; uv run pytest -m live    # testes contra Vaultwarden e Zabbix reais
uv run ruff check . && uv run ruff format --check .
```

O plugin não faz parte do workspace do uv, pois depende do NetBox. Para desenvolvê-lo, siga a seção [Instalação](#instalação) usando `pip install -e` (modo editável) no venv de um NetBox local. O `contrib/netbox_configuration_snippet.py` é um exemplo de `PLUGINS_CONFIG` que lê os segredos do `.env` da raiz: copie `.env.example` e preencha. Os pacotes que usam variáveis de ambiente também têm um `.env.example` com a sua parte.
