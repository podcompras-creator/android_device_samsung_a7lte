# Build completo do LineageOS 16 para a7lte

Os scripts não tratam falta de disco como encerramento do desenvolvimento.
`--manifest-only`, os testes, a auditoria de policy e o kernel são independentes
do download completo. A árvore local `android/` é um overlay, não uma plataforma.

## Host

Use Linux x86_64 com aproximadamente 250–300 GiB livres para fontes/intermediários,
16 GiB de RAM ou mais e swap adequado. O limiar padrão antes do sync é 200 GiB;
isso é uma reserva inicial, não garantia de capacidade final. Python 3.9+ executa
as ferramentas deste port; Python 2.7 atende ferramentas legadas do Android 9.
O build usa o JDK8 entregue pela plataforma em vez do Java21 do host atual.

`Containerfile` descreve um userspace Ubuntu22.04 com dependências de Pie, Python2
e Python3. O arquivo foi preparado, mas a imagem inteira não foi construída
neste disco pequeno. Em uma máquina com Docker e armazenamento adequado:

```sh
docker build -f Containerfile --build-arg BUILDER_UID="$(id -u)" \
  --build-arg BUILDER_GID="$(id -g)" -t a7lte-pie-builder .
docker run --rm -it -v /volume-grande:/work -w /work a7lte-pie-builder bash
```

Monte também a pasta deste projeto sob `/work`, ou extraia o pacote atualizado
ali. Não execute o build como root. Se o host já tiver as dependências, Docker
não é necessário. O bootstrap de pacotes do container não é um snapshot imutável
do APT; para reprodução binária registre também imagem/digest, pacotes e host.

## Sincronização e fontes

```sh
scripts/sync-platform.sh --tree /volume-grande/lineage16 --manifest-only
scripts/sync-platform.sh --tree /volume-grande/lineage16 --sync --jobs 4
```

O launcher oficial `repo` está incluído com licença e SHA-256. O manifesto base
é fixado em `manifests/platform.lock.json`, o kernel/comum/compilador e dependências
locais em commits completos. O manifesto base contém branches móveis de outros
projetos: depois do primeiro sync completo, o script grava o snapshot de **todos**
os commits em `logs/platform/<run-id>/a7lte-platform.lock.xml`. Para repetir exatamente
essas revisões em outra pasta:

```sh
scripts/sync-platform.sh --tree /volume-grande/replay --sync \
  --locked-manifest /caminho/salvo/a7lte-platform.lock.xml --jobs 4
```

Esse snapshot completo ainda não existe nesta entrega porque não houve sync
integral. O que foi executado aqui: repo init, expansão/check do manifesto,
replay standalone pequeno e sync de sete dependências selecionadas. Logs em
`logs/dependencies/` e `logs/platform/` distinguem cada operação.

Após o sync, `apply-overlay.py` verifica os HEADs esperados e aplica os patches
Samsung comum, kernel e policy Qualcomm; instala o defconfig A7 e a árvore local.
Reexecuções reconhecem patches já aplicados. Alterações locais conflitantes e
symlinks em conteúdo gerenciado causam erro, sem `reset --hard` ou limpeza forçada.
Para reaplicar somente o port:

```sh
python3 scripts/apply-overlay.py --tree /volume-grande/lineage16 --check-only
python3 scripts/apply-overlay.py --tree /volume-grande/lineage16
```

Os arquivos finais de dispositivo estão incluídos no pacote; não é necessário
baixar referências CM13 para aplicar o overlay. Para **regenerar** esses arquivos
sem um checkout anterior, use `fetch-reference-sources.py` e `prepare-device.py`.
As fontes CM13 são referências Samsung A7, nunca componentes OPPO.

## Stock, vendor e layout

Siga `firmware-sources.md`, `unpack-stock.md`, `blobs.md` e `partitions.md` para
obter/extrair CSB1, revisar o plano de módulos e gerar vendor. Depois de obter
PIT, boot, recovery e SYSTEM reais:

```sh
python3 scripts/verify-stock-layout.py --pit /stock/A7.pit \
  --boot /stock/boot.img --recovery /stock/recovery.img \
  --stock-build-prop /stock/system/build.prop --sector-size 512 \
  --makefile /volume-grande/lineage16/device/samsung/a7lte/partition-sizes.mk \
  --output /stock/layout.json
```

O tamanho de setor 512 precisa ser confirmado na origem; não use esse parâmetro
para adivinhar geometria. Nenhum `PIT_VERIFIED` vazio libera o build. A verificação
é offline, não autentica Samsung nem testa o aparelho. O pipeline compara também
os hashes atuais dos arquivos vendor selecionados antes de empacotar imagens.

## Compilações com logs

```sh
scripts/build-rom.sh --tree /volume-grande/lineage16 --target nothing --jobs 4
scripts/build-rom.sh --tree /volume-grande/lineage16 --target kernel --jobs 4
scripts/build-rom.sh --tree /volume-grande/lineage16 --target policy --jobs 4
scripts/build-rom.sh --tree /volume-grande/lineage16 --target images --jobs 4 --layout /stock/layout.json
scripts/build-rom.sh --tree /volume-grande/lineage16 --target bacon --jobs 4 --layout /stock/layout.json
```

`nothing` testa o grafo completo quando a plataforma está presente. `policy`
seleciona `sepolicy`; `images` seleciona bootimage/recoveryimage/systemimage;
`bacon` gera a distribuição Lineage. Layout é exigido apenas por imagens/bacon.
Sem vendor real, mesmo metas de diagnóstico podem falhar na leitura do produto;
o script não fabrica blobs ou ativa `ALLOW_MISSING_DEPENDENCIES` para mascarar isso.
Nunca desliga `neverallow`. Logs e códigos de saída ficam em `logs/platform/`.

Este conjunto ainda requer executar o build Android completo e corrigir quaisquer
erros de módulos, símbolos, recursos/VINTF e policy dividida que ele revelar.
SELinux compilado isoladamente não é teste de boot/enforcing, nem substitui a
policy final embutida na imagem. Qualquer ZIP/imagem gerado será experimental
até testes no SM-A700FD e validação dos procedimentos de recuperação/EFS.
