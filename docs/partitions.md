# Partições e cabeçalhos stock: verificação offline

Na primeira etapa não havia PIT ou imagens stock. Na continuação de 2026-11-08,
foram recuperados diretamente do Samsung FUS os componentes completos boot.img,
recovery.img e A7LTE_EUR_OPEN.pit do pacote CSB1/ZTO exato. Cinco tamanhos fixos
agora têm evidência real; USERDATA continua pendente porque seu PIT usa contagem
zero, isto é, fill-to-end. Nenhum tamanho foi inventado para essa partição.

`verify-stock-layout.py` lê arquivos locais. Não comunica com o telefone, não
executa Heimdall/Odin, não grava partições e não modifica os arquivos stock.
Sua finalidade é gerar `partition-sizes.mk` a partir de evidência fornecida e
registrar hashes que o script de build pode conferir antes de empacotar imagens.
A ausência dessa evidência não deve bloquear compilação de bibliotecas, política
ou outros alvos que não produzem imagens de partições.

## Uso com arquivos da mesma fonte stock

No aparelho, o tamanho lógico de setor deve ser conferido, por exemplo com
`blockdev --getss /dev/block/mmcblk0` em um recovery autorizado pelo usuário.
O programa exige `--sector-size 512` explícito; não deduz esse número do campo
`Partition Block Size/Offset` do PIT. No MMC esse campo representa o setor
inicial, enquanto o tamanho da partição é `block_count * sector_size`.

```sh
python3 scripts/verify-stock-layout.py \
  --pit stock/SM-A700FD.pit \
  --boot stock/boot.img \
  --recovery stock/recovery.img \
  --stock-build-prop stock/system/build.prop \
  --sector-size 512 \
  --makefile /builder/lineage16/device/samsung/a7lte/partition-sizes.mk \
  --output /builder/layout-csb1.json
```

O `build.prop` precisa declarar `ro.product.model=SM-A700FD` e a PDA ou versão
incremental `A700FDXXS1CSB1`. O usuário deve fornecer PIT, imagens e build.prop
provenientes do mesmo pacote stock legítimo ou da mesma instalação stock do
aparelho. Uma string de propriedade não autentica criptograficamente o firmware.

O relatório JSON tem `layout_format=1`, `model`, `firmware`, `layout_verified`,
`partition_sizes`, `makefile.path`, `makefile.sha256` e `provenance` com caminhos e
SHA-256 do PIT, boot, recovery e build.prop. `layout_verified=true` significa
somente que as verificações offline descritas abaixo passaram para os arquivos
fornecidos. Não significa ROM funcional, firmware autenticado nem teste de flash.

## Verificações implementadas

- Magic PIT `0x12349876`, cabeçalho de 28 bytes, entradas de 132 bytes, número de
  entradas plausível e tabela completa. Padding zero é aceito; a cauda opaca de
  256 bytes do PIT oficial só é aceita com evidência FUS e hashes correspondentes.
  Essa aceitação não verifica uma assinatura Samsung.
- Strings de tamanho fixo terminadas, nomes seguros e ausência de nomes
  duplicados no mesmo tipo de dispositivo/binário.
- BOOT, RECOVERY, SYSTEM, USERDATA, CACHE e PERSIST presentes uma única vez no
  tipo AP/MMC. Comprimentos fixos são positivos e não podem se sobrepor. USERDATA
  zero só é permitido com `--allow-partial-layout`, gerando relatório parcial e
  sem transformar um valor desconhecido em tamanho válido.
- Tamanhos gerados usam contagem de setores MMC multiplicada por 512. O setor
  inicial não é interpretado como tamanho de bloco em bytes.
- Imagens boot/recovery precisam ter magic `ANDROID!`, kernel e ramdisk não
  vazios, payload completo e tamanho total compatível com as partições PIT.
- Cabeçalho legado Samsung/v0: base `0x80000000`, endereço de kernel base+`0x8000`,
  ramdisk base+`0x02000000`, tags base+`0x01e00000`, página 2048. Esses valores
  correspondem à configuração Samsung comum já usada pelo kernel compilado.
- Se o cabeçalho declara DT separado, a região precisa começar com `QCDT`.
  Cabeçalhos modernos v1/v2 ou formatos Samsung diferentes são rejeitados com
  indicação para inspeção manual; o programa não os converte silenciosamente.

As assinaturas Samsung/Odin, o conteúdo dos DTBs, o CSC, a autenticidade do
arquivo e o funcionamento no hardware não são validados por esse utilitário.
O parser é conservador e pode rejeitar um PIT legítimo com convenções diferentes;
nesse caso é necessário inspecioná-lo, sem remover as verificações às cegas.

## Fontes do formato

Lidas em 2026-11-07:

- [Heimdall libpit.h](https://github.com/Benjamin-Dobell/Heimdall/blob/master/libpit/source/libpit.h):
  `kDataSize=132`, `kHeaderDataSize=28`, `kDeviceTypeMMC=2` e `kFileIdentifier`.
  SHA-256 do arquivo consultado:
  `af62bc656d0ec37860ba31c5c3df9b724adb47a2bc1a2819e8b036137f8996fe`.
- [Heimdall libpit.cpp](https://github.com/Benjamin-Dobell/Heimdall/blob/master/libpit/source/libpit.cpp):
  offsets dos campos em `PitData::Unpack`.
  SHA-256: `7c91c93aeca6966f2375f8d1b11077e33c2f4172ea1f807c413bf65e63f3ddc1`.
- [LineageOS Samsung mkbootimg.mk, lineage-16.0](https://github.com/LineageOS/android_hardware_samsung/blob/lineage-16.0/mkbootimg.mk):
  geração de DT separado, página de kernel e limites de imagens Samsung.
  SHA-256: `ec5a2b6554327517eb7405c7f18d3fb621478c94939db0a8ed5036f308b3b234`.

Heimdall descreve o campo ambiguamente como bloco/tamanho ou offset. Por isso a
unidade MMC é uma entrada explícita conferida no aparelho, não uma inferência do
nome do campo nem uma alegação de que o código Heimdall determina a unidade.

## Testes executados

`python3 -m unittest discover -s tests -p test_stock_layout.py -v`

Cinco testes com fixtures sintéticas passaram: unidades de setor, PIT truncado,
magic/contagem/padding inválidos, sobreposição/nome inseguro, geometria/truncamento
boot, imagens maiores que a partição e identidade de modelo/firmware incorreta.
Não foram utilizados dados stock reais e nenhum resultado sintético é uma
validação do SM-A700FD físico.

## Correção após exercício real de mkbootimg (2026-11-08)

O campo de 32 bits no offset 44 é a versão do Android e nível de patch,
mesmo quando o campo no offset 40 carrega `dt_size` legado Samsung. O parser
agora decodifica esse campo em vez de rejeitar todo valor diferente de zero.
O novo teste usa versão 9.0.0 e patch 2019-02 no cabeçalho Samsung real gerado
pelo empacotador Pie. Valores 1/2 no offset 40 continuam sendo tratados como
cabeçalhos modernos não suportados; DT legado precisa ter payload QCDT válido.
Dois testes de regressão específicos passaram em `test_boot_os_version.py`;
a suíte anterior não foi repetida para essa alteração.

## Evidência oficial recuperada em 2026-11-08

O método FUS autenticado, as faixas HTTPS e os hashes dos componentes estão em
`logs/phase3-firmware/official-components-20261108/components-result.json`.
A consulta oficial retornou modelo SM-A700FD, CSC ZTO, AP A700FDXXS1CSB1 e estado
S00. A recuperação parcial do ZIP contém bytes completos dos três componentes,
mas não verificou o CRC do ZIP inteiro nem o MD5 do TAR completo. O verificador
não transforma essa limitação em uma afirmação de assinatura/autenticidade
criptográfica verificada.

```sh
python3 scripts/verify-stock-layout.py \
  --pit logs/phase3-firmware/official-components-20261108/A7LTE_EUR_OPEN.pit \
  --boot logs/phase3-firmware/official-components-20261108/boot.img \
  --recovery logs/phase3-firmware/official-components-20261108/recovery.img \
  --fus-components logs/phase3-firmware/official-components-20261108/components-result.json \
  --sector-size 512 --allow-partial-layout \
  --makefile android/device/samsung/a7lte/partition-sizes.mk \
  --output logs/phase3-boot/official-layout-partial.json
```

O parser confere estado S00, modelo/CSC/versão AP exatos e tamanho/SHA-256 de
cada componente antes de usar essa evidência em vez de um build.prop inexistente.
Não foi fabricado build.prop de SYSTEM. Os valores fixos obtidos do PIT são:

| Partição | Bytes |
| --- | ---: |
| BOOT | 13.631.488 |
| RECOVERY | 15.728.640 |
| SYSTEM | 2.631.925.760 |
| CACHE | 209.715.200 |
| PERSIST | 8.388.608 |
| USERDATA | Indeterminado: contagem 0 / fill-to-end |

O relatório marca `ready_for_boot_recovery=true`,
`fixed_partition_sizes_verified=true` e `layout_verified=false`. O makefile
gerado deixa USERDATA vazio. A posição SGPT do PIT não foi usada para inventar
capacidade física; essa partição precisa ser medida no SM-A700FD ou em GPT
verificado do mesmo dispositivo. O tamanho lógico de setor 512 permanece uma
premissa explícita da interpretação MMC e deve ser confirmado no alvo.

Boot e recovery stock têm exatamente os endereços e página já usados pelo
kernel nativo. Seus identificadores SHA-1 de cabeçalho foram recalculados e
conferidos. O PIT tem 31 entradas mais 256 bytes opacos; boot/recovery têm
`SEANDROIDENFORCE` seguido por 256 bytes opacos. As caudas foram registradas com
hash, mas suas assinaturas não foram autenticadas. Dois testes novos em
`test_fus_layout.py` cobrem hashes divergentes e PIT assinado/fill-to-end com
fixtures sintéticas; não foi repetida a suíte antiga.
