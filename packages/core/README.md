# netbox-compare-core

Modelo canônico e contratos dos módulos do netbox-compare. Não depende de Django nem do NetBox, então os módulos podem ser desenvolvidos e testados sem um NetBox instalado.

## Conteúdo

- `canonical.py`: os três tipos de objeto (equipamento, interface, endereço IP), o catálogo de campos e o valor `NOT_OBSERVED` ("não observado", diferente de vazio).
- `connection.py`: `ConnectionModule` e `Session`, o contrato dos módulos de conexão.
- `credentials.py`: `CredentialsProvider`, que resolve um equipamento em (host, usuário, senha).
- `notification.py`: `NotificationModule` e o `RunReport` enviado ao fim de cada execução agendada.
- `entrypoints.py`: os grupos de *entry points* em que os módulos se registram.

## Instalação

Instalado como dependência do plugin e dos módulos. No venv do NetBox:

```bash
sudo /opt/netbox/venv/bin/pip install ./packages/core
```

## Criando um módulo

Crie um pacote que dependa de `netbox-compare-core`, implemente a classe base do tipo de módulo e registre-a no grupo correspondente:

| Tipo | Classe base | Grupo de entry point |
|---|---|---|
| Conexão | `ConnectionModule` | `netbox_compare.connections` |
| Credenciais | `CredentialsProvider` | `netbox_compare.credentials` |
| Notificação | `NotificationModule` | `netbox_compare.notifications` |

```toml
[project.entry-points."netbox_compare.connections"]
meu_modulo = "meu_pacote.module:MeuModulo"
```

O nome do entry point (`meu_modulo`) é o que se usa em `"module"` no `PLUGINS_CONFIG`. O construtor recebe o dicionário `config` dessa entrada.

## Testes

```bash
uv run pytest packages/core
```
