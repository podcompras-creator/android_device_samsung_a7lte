# Auditoria real do empacotamento Samsung, sem imagem para flash

A continuação recuperou imagens oficiais CSB1 e confirmou a geometria de boot.
O stock usa QCDT v3; a configuração ativa foi ajustada para v3, e o dt.img v2
anterior continua preservado. Os testes sintéticos abaixo foram executados
separadamente da inspeção do stock real.

Foram compiladas ferramentas host e executados os dois alvos da receita
`hardware/samsung/mkbootimg.mk` do LineageOS 16. Os insumos foram o `zImage` e o
`dt.img` já preservados, mais um ramdisk **sintético, contendo somente um arquivo
README e sem `/init`**. O kernel não foi recompilado e nenhum componente OPPO
foi usado.

Os resultados estão em `artifacts/boot-audit/final/`, com `NONFLASHABLE` no nome.
Esses arquivos exercitam o formato binário e a receita de empacotamento; não são
boot/recovery utilizáveis, não contêm Android init, não foram assinados para
flash e não constituem uma ROM. O teto de 32 MiB da fixture é arbitrário e serve
apenas para executar o teste da macro de limite da receita. Ele **não** é tamanho
de partição obtido do SM-A700FD.

## Fontes fixadas e execução

`tooling/boot-sources.lock.json` registra as URLs, commits e hashes dos arquivos
originais usados, que estão preservados em `tooling/boot-sources`:

- `LineageOS/android_system_core`, commit
  `976019d07ad1c007043b78450857f428a1440f06`: `mkbootimg/mkbootimg` e
  `mkbootimg/include/bootimg/bootimg.h`.
- `LineageOS/android_hardware_samsung`, commit
  `871d3f4777603ff6c33a021fc38c9b2265c54f83`: `mkbootimg.mk`.
- `LineageOS/android_system_tools_dtbtool`, commit
  `a2b9e476be722a49ef7a056a0548072cb6babb75`: `dtbtool.c`.

O `mkbootimg` Pie desta revisão é um programa Python, não um fonte C. Ele foi
executado sem alterações. O `dtbToolLineage` foi compilado nativamente com GCC;
um pequeno programa C++ também compilou o cabeçalho real Android para verificar
por `static_assert` os offsets e o tamanho do cabeçalho. O helper não substitui
o mkbootimg da plataforma em um build completo.

```sh
tooling/build-boot-tools.sh
python3 scripts/test-samsung-boot.py --output artifacts/boot-audit/NOVA-EXECUCAO
```

São necessários GCC, G++, GNU make, Python 3 e um `dtc` já disponível. O teste
usa por padrão `out/kernel/scripts/dtc/dtc`, produzido no build original; em
outro ambiente pode-se fornecer `--dtc /usr/bin/dtc` do pacote oficial
`device-tree-compiler`. O script recusa sobrescrever um diretório de auditoria
existente. Não é preciso baixar Android completo nem recompilar o kernel.

A receita Samsung é incluída por GNU make, não reimplementada pelo teste. Os
argumentos fornecidos são: base `0x80000000`, kernel offset `0x8000`, ramdisk
`0x02000000`, tags `0x01e00000`, página 2048, cabeçalho 0, DT separado, versão
9.0.0 e patch de fixture 2019-02-01. Versão/patch desta fixture não afirmam nível
de atualização ou segurança de uma ROM entregue.

A receita acrescenta o trailer literal `SEANDROIDENFORCE` (16 bytes). O ramo sem
Loki da receita upstream executa `echo patch ...` e tenta copiar um `.lok`
inexistente com `|| true`; os avisos de `cp` nos logs são desse comportamento
original. Nenhum patch de bootloader ou imagem Loki foi produzido.

## Resultados obtidos

- Compilação host do `dtbToolLineage` e do verificador de layout C++: passou.
- Reempacotamento dos cinco DTBs em QCDT v2: byte a byte igual ao `dt.img`
  preservado, SHA-256
  `a8015dab6afd771deb363665e90b969929039cd50a67006437dd9ad105392e79`.
- Receita Samsung boot e recovery: executada com saída 0; cada fixture tem
  7.073.808 bytes. As duas são iguais porque recebem exatamente os mesmos
  insumos sintéticos. Não representam sistemas boot e recovery distintos.
- SHA-256 das fixtures:
  `760f7e2ec1dd50b7e081fd3dcacc6d6da6ce101bf24c0784cce303f6b2a79bba`.
- Identificador SHA-1 de cabeçalho conferido conforme a ordem upstream:
  kernel+size, ramdisk+size, second+size e DT+size. SHA-1 resultante:
  `c7a40eb46d4f6cb3f944d8aa84f92dcd68ac809c`.
- Offsets no arquivo: kernel 2048; ramdisk 6.035.456; DT 6.037.504;
  trailer 7.073.792. Todos os payloads foram comparados byte a byte com os
  insumos; o tamanho e hash do kernel e DT originais continuam iguais.
- QCDT: 15 entradas válidas, cinco DTBs únicos; conferidos limites,
  alinhamento, magic FDT e tamanho de cada entrada.
- Três mutações específicas foram rejeitadas: kernel corrompido, trailer
  truncado e cabeçalho moderno v1 interpretado indevidamente como tamanho DT.
- Dois novos testes de regressão do campo de versão OS passaram. O exercício
  real mostrou que o offset 44 pode ser não zero no formato Samsung; o parser
  `verify-stock-layout.py` foi corrigido para decodificá-lo.

Relatórios completos: `logs/phase3-boot/boot-audit-result.json`,
`boot-roundtrip.json`, `recovery-roundtrip.json`, `cli-inspection.json`,
`os-version-regression.log` e `packaging-run.log`.

A primeira execução revelou uma exigência do dtbTool antigo: o diretório de
entrada precisa terminar com `/`. O programa retorna zero mesmo ao encontrar
zero DTBs. O script passou a fornecer a barra e a conferir a existência e o hash
do resultado. A tentativa inicial está em `artifacts/boot-audit/attempt-01` e
`logs/phase3-boot/packaging-run-01.log`; não foi apresentada como execução aprovada.

## Inspeção independente

```sh
python3 scripts/inspect-samsung-boot.py \
  artifacts/boot-audit/final/a7lte-BOOT-PACKAGING-NONFLASHABLE.img \
  --kernel artifacts/zImage \
  --ramdisk artifacts/boot-audit/final/ramdisk.MARKER-ONLY-NONFLASHABLE.cpio.gz \
  --dt artifacts/dt.img
```

O inspetor não executa conteúdo nem grava partições. `--extract NOVO_DIRETORIO`
opcional grava somente arquivos de nome fixo com os payloads, para inspeção
manual. Ele aceita o formato legado com QCDT v2 e trailer Samsung exato; outros
formatos ou assinaturas stock devem ser investigados, não convertidos às cegas.

A compatibilidade operacional com o bootloader e a inicialização do SM-A700FD
**continua sem comprovação**. A geometria de cabeçalho e os seletores DT agora
foram comparados com o stock real, conforme a seção seguinte; isso não substitui
o teste físico nem prova compatibilidade dos drivers/HALs.

## Inspeção dos componentes stock oficiais

Foram inspecionados os bytes completos de boot.img, recovery.img e PIT recuperados
pelo agente de firmware diretamente do Samsung FUS exato CSB1/ZTO. O relatório
FUS registra recuperação parcial do ZIP, sem CRC global do ZIP/TAR validado.

- Boot stock: 11.895.056 bytes, SHA-256
  `01e1ff5ad1d1530cb922ae884f6796794e3dadae620341107fd5ebc993e27e12`.
- Recovery stock: 13.490.448 bytes, SHA-256
  `ff6668d81c6dd5b29762858609f68bca83afe2d8eef26ad0b75f83d19df5f82c`.
- Base 0x80000000, kernel 0x80008000, ramdisk 0x82000000, tags 0x81e00000 e
  página 2048 conferem exatamente com a configuração nativa.
- Os SHA-1 dos cabeçalhos stock conferem com os payloads extraídos:
  boot `ce2cf82e5f2340bb03c45aeea8348cfb9534cbad`, recovery
  `068f5de4ba49a5b47ca4faa303783f0ad576aa5b`.
- Ambos contêm QCDT **v3**, 15 entradas e cinco DTBs únicos. Os seletores são
  SoCs 239/241/263, plataforma 0x0ef08ff1, revisões 1/3/4/5/6 e quatro campos
  PMIC zero. O candidato nativo v3 usa os mesmos seletores/PMICs.
- Stock tem o marcador Samsung mais 256 bytes opacos posteriores. O inspetor
  os aceita somente com `--allow-signature-tail`, registra hash e afirma
  explicitamente que a assinatura não foi verificada.

A opção ativa A7 `BOARD_DTBTOOL_ARGS := -3` foi ajustada a essa evidência. Um novo
candidato `artifacts/boot-audit/dt-QCDTv3.img` foi gerado dos cinco DTBs nativos,
sem recompilar kernel e sem substituir o dt.img v2 original. Seu SHA-256 é
`74270d174fd2f7e55f9d50826e573224a1d993cbe7661e3d5bc692bafe9dc3ed`.
A receita Samsung com esse candidato passou novamente em
`artifacts/boot-audit/qcdt3/*NONFLASHABLE.img`; as fixtures continuam sem init.
Essas fixtures têm SHA-256
`935f4fcbae9d11ebf71a5eea95a7496b5c23cfb40f9c521bd07ab82d1330dc6c`.

```sh
python3 scripts/test-samsung-boot.py \
  --dt-image artifacts/boot-audit/dt-QCDTv3.img \
  --output artifacts/boot-audit/NOVA-EXECUCAO-V3
```

O conteúdo dos DTBs não é idêntico ao stock. Foram preservados hashes e diffs
DTS por revisão em `logs/phase3-boot/stock-dtbs`. As diferenças incluem timeout
GPU, clock/alimentação NFC e calibração de bateria; números de phandle também
mudam. Não foram transplantados valores stock às cegas para um kernel de ramo
mais novo. Seletores iguais não comprovam que o bootloader escolherá corretamente
um DTB nem que os drivers funcionarão no aparelho.

`extract-stock-ramdisk.py` descompactou os ramdisks reais e materializou somente
textos de auditoria init/fstab/ueventd/default.prop e contextos. Inventários com
hash estão em `logs/phase3-boot/stock-ramdisks/{boot,recovery}`. O programa não cria
symlinks/dispositivos, não copia `/init`, não instala ramdisk Samsung no produto
Lineage e não mistura o kernel stock à ROM. A árvore de dispositivo usa esses
textos como evidência para comparação, não como substituto do init Pie.

Relatórios adicionais: `official-boot-inspection.json`,
`official-recovery-inspection.json`, `official-layout-partial.json`,
`qcdt-stock-native-comparison.json` e `test-output-v3.json`.
