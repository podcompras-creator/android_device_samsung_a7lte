# Blobs Samsung A7: pipeline reproduzível e limites

Nenhum blob do OPPO foi obtido ou instalado. O inventário de 257 candidatos deriva
do vendor Samsung A7 CM13 registrado em `logs/original-a7lte-vendor-blobs.mk`.
Essa lista **não comprova** que os arquivos existam no CSB1 ou que funcionem no Pie.
O firmware real ainda precisa ser obtido e extraído.

## Extração e auditoria

`scripts/safe-unpack-stock.py` prepara payloads de ZIP/TAR em uma pasta nova sem
flash, mount ou sudo; consulte `docs/unpack-stock.md` para converter a imagem SYSTEM
com ferramentas legítimas. O extrator abaixo recebe o conteúdo do SYSTEM, com
`build.prop`, `lib/`, `bin/` e `vendor/` diretamente nessa pasta.

```sh
python3 scripts/extract-stock.py /caminho/stock-system --output /caminho/csb1-extracted
python3 scripts/audit-blob-lists.py --output logs/blob-list-reconciliation.json
```

Requisitos: Python 3.9+ e `readelf` (binutils). O extrator recusa modelo diferente de
`SM-A700FD`, fabricante diferente de Samsung, PDA/incremental diferente de
`A700FDXXS1CSB1`, propriedades conflitantes, caminhos com traversal, links que saiam
do SYSTEM e saída não vazia. Links relativos confinados são materializados e
registrados. Links Android absolutos que não resolvam no diretório fornecido não
são seguidos para fora do SYSTEM; prepare uma imagem desmontada segura, sem
reescrever links para o host.

O código não executa os binários proprietários. Copia os candidatos e registra:

- `inventory.json`: origem, destino, SHA-256, tamanho, faltas e identidade de build.
- `elf-dependencies.json`: DT_NEEDED e provedores presentes no
  conjunto extraído ou ainda somente no SYSTEM stock. O inventário também registra
  ELF32 ARM, SONAME e símbolos dinâmicos exportados/indefinidos para comparação
  posterior com a plataforma Pie.
- `vendor-review.candidate.json`: plano inicial **não aprovado** de módulos/arquivos.

Saída `0`: todos os candidatos existem e o exame ELF32 ARM passou. Saída `1`:
inventário gravado, mas existem faltas/ELFs incompatíveis. Saída `2`: erro de
identidade, caminho, ferramentas ou parâmetros. Uma falha pode deixar staging
parcial: preserve-o e use uma nova pasta após corrigir a origem.

PDA AP não identifica CSC. `csc_identity.region_verified_from_metadata` só fica
verdadeiro se houver metadados explícitos ZTO consistentes, em `ro.csc.sales_code`
ou `csc/sales_code.dat`. A ausência desses metadados continua registrada; não se
infere ZTO do número CSB1.

## Geração do vendor para builds diagnósticos

Copie o plano candidato para um novo JSON e revise **cada arquivo**. Defina
`reviewed: true` apenas após resolver conflitos. Para cada entrada, selecione:

- `action: module` e `module: nome`: ELF ou APK prebuilt; nome único. `destination`
  define a instalação sob `/system`, sem remapeamento automático Treble.
- `action: copy`: configuração/firmware/dados não ELF.
- `action: skip` e `reason: texto`: arquivo desnecessário ou fornecido por módulo
  da plataforma; arquivos ausentes só podem ser ignorados dessa forma explícita.

```sh
python3 scripts/generate-vendor.py /caminho/csb1-extracted \
  --plan /caminho/vendor-review.json \
  --output /caminho/android/vendor/samsung/a7lte
```

O gerador verifica novamente os hashes e os ELFs selecionados, não sobrescreve
saídas existentes e produz `Android.mk`, `a7lte-vendor.mk`, `BoardConfigVendor.mk`,
inventário, plano revisado e `vendor-audit.json`. Este último distingue
`ready_for_diagnostic_build` de `release_ready` (sempre falso nesta etapa).
A revisão explícita evita gerar silenciosamente módulos que colidam com AOSP,
HALs HIDL, wrappers da árvore comum ou os symlinks de firmware.

Mapeamentos já registrados na lista:

- `lib/hw/camera.msm8916.so` → `lib/hw/camera.vendor.msm8916.so`; o wrapper Pie
  produz `camera.msm8916.so`.
- `lib/hw/sensors.msm8916.so` → `lib/hw/sensors.vendor.msm8916.so`; o wrapper de
  sensores comum produz `sensors.msm8916.so`.
- Nomes históricos `vendor/firmware/keymaste.*` →
  `vendor/firmware/keymaster/keymaster.*`; confirmar no CSB1 real.

Não instale o `bin/rild` stock por padrão: extraia para evidência, mas selecione
`skip` com motivo e use o RIL compilado do Pie, esperado em `/vendor/bin/hw/rild`.
Os blobs `libsec-ril.so` e `libsec-ril-dsds.so` continuam em `/system/lib`, como
esperado pelos serviços e shims atuais.

## Reconciliação da árvore comum

A lista comum contém 192 entradas, das quais 115 têm caminhos presentes entre os
257 candidatos A7. As 77 restantes precisam de uma decisão baseada no firmware ou
em implementações compatíveis compiladas de fonte. O relatório
`logs/blob-list-reconciliation.json` preserva cada seção/hash e a diferença entre
as listas. A lista comum declara origens J5, Moto, Crackling e Bullhead; seus hashes
**não foram usados como autorização para importar arquivos**. Caminhos iguais
não significam versão de blob igual. Não há `vendor/samsung/msm8916-common`
proprietário automaticamente instalado por este pipeline.

Ainda devem ser verificados com os arquivos CSB1 reais: símbolos indefinidos versus
libs do Pie, namespaces/paths de linker, DT_NEEDED completo, HAL1 de câmera,
interfaces HIDL/RIL/áudio/GPS/DRM/BT, assinaturas APK, init/SELinux e permissões.
O exame ELF não substitui ligação/build completo nem teste no aparelho.

## Testes executados

```sh
python3 tests/test_blob_tools.py
```

20 casos com fixtures sintéticas, incluindo DSOs ARM reais compilados com o
GCC 7.2 já salvo: DT_NEEDED e provedores, recusa de ELF de host, modelo/build/CSC,
traversal, links externos, preservação de saída, arquivos faltantes, verificação de
hash, revisão obrigatória e geração com câmera renomeada. Resultado registrado em
`logs/blob-tools-tests.log`. Esses testes não usam nem validam firmware real.

## Atualização: ABI nativa e schema2

O gerador agora resolve os nomes de módulos de `DT_NEEDED`, protege módulos de
fonte e registra integridade de makefiles/plano no schema2. O ZIP exige uma
auditoria separada das saídas ELF reais. Consulte `docs/native-dependencies.md`;
o relatório vendor sozinho não prova compatibilidade Pie.
