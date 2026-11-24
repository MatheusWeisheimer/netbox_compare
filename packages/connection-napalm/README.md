# netbox-compare-napalm

Módulo de conexão do netbox-compare baseado em [NAPALM](https://napalm.readthedocs.io/). Lê os equipamentos com os *getters* do NAPALM (`get_facts`, `get_interfaces`, `get_interfaces_ip`) e executa comandos avulsos.

Não escreve nos equipamentos: divergências nos seus equipamentos só podem ser corrigidas na documentação.

Entry point: `napalm` (grupo `netbox_compare.connections`).

## Instalação

No venv do NetBox, junto com o core:

```bash
sudo /opt/netbox/venv/bin/pip install ./packages/core "./packages/connection-napalm[vrp]"
```

O extra `[vrp]` instala o driver `napalm-huawei-vrp`. Para outros fabricantes, instale o driver NAPALM correspondente (os drivers nativos, como `ios`, `junos` e `eos`, já vêm com o `napalm`).

O servidor do NetBox precisa alcançar o IP primário dos equipamentos na porta usada pelo driver (normalmente SSH, 22).

## Configuração

```python
"connections": [
    {
        "module": "napalm",
        "config": {
            "platforms": {
                "huawei-vrp": {
                    "driver": "huawei_vrp",
                    "timeout": 60,
                },
            },
        },
    },
],
```

Cada chave de `platforms` é o **slug de uma platform do NetBox**. Equipamentos com outra platform não são comparados por este módulo.

| Chave | Obrigatória | Descrição |
|---|---|---|
| `driver` | sim | Nome do driver NAPALM (`huawei_vrp`, `ios`, `junos`, ...) |
| `timeout` | não | Segundos, padrão 60 |
| `optional_args` | não | Repassado ao driver (ex.: `{"port": 2222}`) |
| `exclude_fields` | não | Campos canônicos que o módulo deve declarar como não lidos nessa platform (ex.: `["interface.mtu"]`). Ficam "não comparáveis". |

## Huawei VRP

O `fixups.py` corrige a saída do driver `huawei_vrp`:

- remove as aspas que o VRP coloca em descrições com espaços;
- lê o estado administrativo da interface em `display interface brief` (o driver usa o estado físico, e uma porta sem link apareceria como desabilitada);
- se `display esn` não existir na versão do VRP, lê o número de série em `display device manufacture-info`.

## Testes

```bash
uv run pytest packages/connection-napalm
```
