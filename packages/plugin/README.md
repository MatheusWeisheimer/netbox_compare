# netbox-compare (plugin)

Plugin do NetBox que compara o estado documentado dos equipamentos com o estado lido deles. Contém os modelos, as telas, os jobs em segundo plano, a lógica de comparação e a API REST.

Ele não fala diretamente com equipamentos, cofres de senha ou sistemas de monitoramento: isso fica com os módulos de conexão, credenciais e notificação, instalados como pacotes separados.

## Requisitos

- NetBox 4.5 ou superior, com o `rqworker` rodando
- Python 3.12 ou superior
- `netbox-compare-core`
- Ao menos um módulo de conexão e um de credenciais

## Instalação

No venv do NetBox, junto com o core e os módulos escolhidos (no mesmo comando):

```bash
sudo /opt/netbox/venv/bin/pip install ./packages/core ./packages/plugin ...
```

Em `configuration.py`:

```python
PLUGINS = ["netbox_compare"]
PLUGINS_CONFIG = {"netbox_compare": {...}}
```

Depois:

```bash
cd /opt/netbox/netbox
sudo /opt/netbox/venv/bin/python manage.py migrate netbox_compare
sudo systemctl restart netbox netbox-rq
```

Reinicie o NetBox e o `rqworker` sempre que instalar, remover ou atualizar um pacote: os módulos são descobertos na inicialização.

O passo a passo completo e as chaves de `PLUGINS_CONFIG` estão no [README da raiz](../../README.md).

## Endereços

- Relatórios: `/plugins/compare/comparisons/`
- Políticas, agendamentos e resultados: menu Plugins → "NetBox Compare"
- Comparação manual: botão "Compare with device running configuration" na página do equipamento
- API REST: `/api/plugins/compare/` (`policies`, `schedules`, `runs`, `comparisons`)

## Testes

Os módulos que não dependem do Django (ex.: `diff.py`) são testados pelo `uv run pytest` da raiz. `tests/conftest.py` simula o NetBox.
