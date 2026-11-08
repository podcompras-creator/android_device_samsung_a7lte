# Ambientes realmente disponíveis nesta sessão

A avaliação usa o ambiente anexado à conversa e o daemon Docker local, não
pressupõe acesso a contas cloud ou servidores não configurados.

- Ambiente selecionado: volume overlay de aproximadamente 8 GiB; espaço livre
  registrado em `logs/phase3-environment/local-builder.json` (cerca de 1,2 GiB).
- Cgroups: 2 CPUs equivalentes, 8 GiB RAM e nenhum swap.
- O runtime expõe ferramentas de compilação parciais; Python2/Java8 completo e
  várias dependências de plataforma não estão preparados neste host.
- Docker foi consultado pelo socket local explícito. Um container oficial
  BusyBox1.37.0, somente leitura, sem rede e descartável, mediu o mesmo volume
  de8 GiB e os mesmos limites de RAM/CPU. Docker não oferece armazenamento de
  build adicional. Imagem usada: digest registrado no log, não um builder Pie.
- Os dispositivos vistos pelo kernel (vda/pmem) não foram formatados/montados;
  não constituem um volume novo autorizado ou maior disponível para este build.
- Só um ambiente foi anexado. Nenhuma identidade de saída cloud, VPN ou servidor
  remoto foi configurado. A API exposta fornece status desse ambiente, mas não
  oferece criação, redimensionamento nem enumeração de outros builders.

A insuficiência do ambiente foi demonstrada; isso não impede os componentes e
as auditorias independentes entregues. Não houve tentativa de sincronizar centenas
de gigabytes no volume pequeno, nem limpeza das fontes/artefatos para simular espaço.

O script somente leitura pode avaliar outro ambiente já disponibilizado:

```sh
python3 scripts/probe-build-environment.py --path /volume-do-build \
  --android-tree /volume-do-build/lineage16 --output builder.json
```

Saída78 significa capacidade/pré-requisitos insuficientes, não erro em uma ROM.
O relatório distingue disco, memória+swap e arquivos de plataforma ausentes.
Use os scripts existentes de sincronização/build quando um builder adequado for
conectado. Não foi contratado ou criado um serviço pago nem solicitado acesso
às contas do usuário nesta sessão.
