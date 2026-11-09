# Preparação autônoma do vendor CSB1 no runner

`ci/prepare-csb1-vendor.py` integra os arquivos reais do SYSTEM fornecido pelo
fetcher, sem buscar blobs históricos nem usar outros aparelhos:

```sh
python3 ci/fetch-csb1-system.py --output /mnt/csb1
python3 ci/prepare-csb1-vendor.py --system /mnt/csb1/system \
  --tree /mnt/lineage --staging /mnt/csb1-vendor-staging \
  --allow-missing-candidates
```

A segunda chamada é o modo diagnóstico forçado solicitado, compatível com
`ALLOW_MISSING_DEPENDENCIES=true`. Não executa o build nem aplica um gate de ZIP.
Sem `--allow-missing-candidates`, qualquer candidato não resolvido que não tenha
um fornecedor de fonte explícito interrompe a geração. O runner pode preservar
um vendor parcial **somente no modo diagnóstico explícito**, sem declarar ROM
funcional nem substituir arquivos ausentes.

## Origem e seleção

O script exige `SM-A700FD`, fabricante Samsung e versão PDA/incremental exata
`A700FDXXS1CSB1`, usando o extrator existente. Se houver
`../fetch-result.json`, exige sucesso, consumo completo do ZIPentry AP, CRC
verificado e SHA-256 do `build.prop` igual ao observado. Esse relatório é copiado
para o staging; não é transformado em alegação de assinatura Samsung verificada.
Sem relatório de aquisição, a auditoria registra explicitamente que só a
identidade das propriedades foi conferida. A região CSC nunca é inferida do AP.

A lista histórica de257candidatos foi ampliada para263 após examinar o
`DT_NEEDED` dos consumidores CSB1 reais. Os seis caminhos adicionais são
candidatos a provedores que a próxima aquisição precisa confirmar. Só bytes
regulares confinados nesse diretório são materializados em uma visão temporária
por hardlink/cópia e fornecidos a `extract-stock.py`. Essa visão não contém
arquivos de outros repositórios. A detecção de dependências nela não pode confirmar
provedores stock fora do conjunto selecionado; a auditoria registra essa limitação.

Links absolutos Android para `/firmware`, `/system` ou qualquer caminho fora do
SYSTEM fornecido não são seguidos no host. Faltas, links externos, fontes não
regulares e ELFs incompatíveis ficam no inventário combinado. No modo forçado,
são omitidos do vendor com `unresolved=true`, `source_provided=false` e motivo
explícito. As faltas de blobs essenciais são listadas separadamente; não são
rebatizadas como módulos de fonte nem preenchidas com arquivos de 2016.

## Regras estáticas revisadas

O plano completo gerado é determinístico e inclui cada candidato. Ele usa os
contratos de fonte existentes e as seguintes decisões adicionais fundamentadas:

- `camera.msm8916.so` e `sensors.msm8916.so` stock recebem destinos
  `camera.vendor.msm8916.so` e `sensors.vendor.msm8916.so`; os wrappers de fonte
  mantêm os nomes principais.
- `rild`, `libril`, áudio CAF, GPS comum e common_time permanecem compilados de
  fonte conforme `scripts/native-contracts.json`.
- `libtinyalsa`, `libaudioroute` e `libreference-ril` têm fornecedores de fonte na
  plataforma. `libsecril-client` é definido pelo hardware Samsung selecionado,
  incluído com `BOARD_VENDOR=samsung`; não se instala uma segunda cópia stock.
  A compatibilidade ABI desses fornecedores ainda precisa do build real.
- `librmnetctl` é fornecido pelo repositório Qualcomm dataservices selecionado,
  commit `c2c036451782b6193923be8d6311ae1a43fa4a73`; sua segunda definição stock
  é omitida. A regeneração local com o inventário e os bytes CSB1 reais passou,
  mantendo237arquivos selecionados e os hashes dos demais componentes.
- Os cinco destinos `vendor/firmware/keymaster/keymaster.*` pertencem aos links
  gerados pelo `msm8916-common/Android.mk` para `/firmware/image/keymaste.*`.
  Eles são omitidos como saídas geradas de fonte, sem substituir firmware montado.
- `libaudio-ril.so`, `libtime_genoff.so` e demais candidatos proprietários sem
  fornecedor de fonte comprovado são mantidos quando existem no SYSTEM CSB1.

Módulos ELF têm nomes/destinos baseados nos arquivos reais e dependências
`DT_NEEDED` geradas pelo mecanismo existente. Colisões ou erros de ELF não são
resolvidos com stubs. A execução não grava CP, BL, modem ou partições do aparelho.

## Evidência preservada

No staging: `source-probe.json`, lista de arquivos disponíveis,
`extraction/inventory.json`, hashes por arquivo, plano completo
`vendor-review.json` e `generation-audit.json`.

Em `TREE/vendor/samsung/a7lte`: makefiles e bytes realmente selecionados,
`stock-inventory.json`, `vendor-review.json`, `vendor-audit.json` e
`ci-generation-audit.json`. Os dois relatórios destacam modo forçado, faltas e
blobs essenciais ausentes. `pie_symbol_compatibility_verified`, `device_tested`,
`ready_for_functional_rom` e `release_ready` continuam falsos.

Saídas existentes não são sobrescritas. Após uma falha, preserve o staging e use
uma pasta nova. O SYSTEM original não é modificado e a visão temporária é removida.

## Verificação desta etapa

`tests/test_ci_vendor_new.py` usa somente fixtures sintéticas e pequenos DSOs ARM
reais compilados para os testes. Confere seleção/hash/renomes, proteção de módulos
de fonte, faltas estritas e forçadas, links externos de arquivos e diretórios,
CSC externo, identidade incorreta, evidência de fetch malsucedida e preservação
de vendor existente. O resultado fica em `logs/ci-vendor-targeted-tests.log`.
O firmware completo não foi baixado nem recompilado localmente por esses testes.

Foram executados 10 casos iniciais e mais 4 casos novos após reforçar a validação
de caminhos e da aquisição: escape pelo diretório pai do vendor, contagens do
inventário combinado, exigência de CRC do AP e preservação de relatório bem
sucedido com hash exato do `build.prop`. Os quatro últimos estão registrados em
`logs/ci-vendor-followup-tests.log`; os testes antigos do projeto não foram repetidos.

O workflow salva imediatamente o vendor adquirido no cache do Actions,
independentemente de sucesso posterior do Android. O cache é invalidado por
alterações no extrator, gerador, contratos de fonte e lista de candidatos. Ao restaurar, makefiles,
plano, inventário e cada blob selecionado são conferidos por SHA-256. Isso evita
baixar o mesmo firmware após uma falha posterior; não verifica ABI nem hardware.

O artefato `a7lte-csb1-vendor-4` da execução42541519000 foi baixado e conferido:
238arquivos selecionados,250extraídos na aquisição original e nenhum essencial
marcado ausente. A auditoria ELF identificou seis provedores adicionais:
`libOpenCL`, `libexifa`, `libflp`, `libqmi_client_helper`,
`lib_SA_GoogleFX_ver119k` e `libsecaudioinfo`. Os consumidores e seus hashes
estão em `logs/csb1-vendor-real-dependency-audit.json`. A ausência de faltas
na lista essencial original não comprova o fechamento dessas dependências.

Na execução42544239502, os seis provedores foram encontrados no SYSTEM real,
todos passaram na conferência SHA-256 e o vendor passou a243arquivos selecionados.
Somente os dois candidatos RenderScript anteriores continuaram ausentes.
A evidência por arquivo está em `logs/csb1-vendor-run6-providers.json`.

Para analisar os conflitos GPS/protobuf, a geração também pode preservar os
originais `lib/libgps.utils.so` e `lib/libprotobuf-cpp-full.so` em
`stock-reference/`. Esses arquivos têm hashes e proveniência próprios e não
recebem regras de módulo nem de instalação na imagem. O verificador do cache
confere as referências presentes e registra ausências, mantendo compatibilidade
com os caches produzidos antes dessa extensão. Oito testes novos dessa extensão
passaram; a preservação dos originais será exercitada na aquisição seguinte.
