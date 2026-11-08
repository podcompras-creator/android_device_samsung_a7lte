# Auditoria de ABI e bloqueio do ZIP a7lte

## Evidência real obtida

Foram baixados **15 ELFs específicos do vendor comunitário Samsung A7**, totalizando
**7.335.172 bytes**, do commit fixo
`0f039d3c6c76b8fc9ece945f54a09056a09d9dcf` de
`MSM8939-Samsung/android_vendor_samsung_a7lte`. São arquivos da época de 2016,
anteriores ao CSB1 de 2019: **não são apresentados como CSB1, não foram instalados
no vendor e nenhum executável deles foi executado**. Não foram usados componentes
do OPPO nem substitutos de outros aparelhos.

`scripts/audit-historical-a7.py --fetch` reproduz o download limitado a 100 MiB;
sem `--fetch`, verifica e reanalisa os arquivos salvos. Cada tamanho e Git blob
SHA-1 é conferido contra a árvore do commit; SHA-256, URL e saída estrutural do
`readelf` ficam em `verification/historical-a7/elf-audit.json`.
`findings.json` contém observações derivadas dos símbolos reais:

- Câmera A7 importa exatamente
  `_ZN7android16CameraParameters26PIXEL_FORMAT_YUV420SP_NV21E`, implementado no
  `camera_shim.c` da base comum. Isso confirma uma necessidade concreta daquele
  shim para **esta amostra histórica**, sem comprovar o comportamento do CSB1.
- `libloc_api_v02.so` depende de `sec_gps_conf`; os fornecedores históricos são
  `libgps.utils.so` e a família Samsung `libloc*`. Os identificadores
  `sec_gps_conf`, `loc_read_sec_gps_conf` e `loc_secgps_default_parameters` não foram
  encontrados nos 77 arquivos da implementação GPS comum. Portanto não basta
  combinar o blob GPS histórico com as bibliotecas comuns compiladas de fonte.
  É necessária adaptação fundamentada desses contratos ou prova de ABI diferente
  no CSB1. Não foram criadas funções vazias para mascarar o problema.
- Os dois `libsec-ril` importam campos globais `RIL_SIM_SAP_*_fields` e símbolos
  C++ de protobuf. A existência de `libril.so`/`libprotobuf-cpp-full.so` não resolve
  a questão: os símbolos exatos devem existir nas saídas Pie reais. O `libril`
  histórico da amostra também não exporta esses campos SAP; outro fornecedor
  gerado/ligado precisa ser identificado na plataforma.
- O repositório histórico não tem ELF `keystore`/`keymaster` para tratar como
  solução pronta. `libQSEEComAPI.so`, a implementação keystore compilada de fonte
  e os firmwares Keymaster precisam ser conferidos juntos.
- Os símbolos específicos dos shims de GPS/Secril não aparecem como importações
  diretas nesta amostra. Isso não autoriza removê-los para o CSB1 desconhecido.

## Gerador corrigido e integridade

`generate-vendor.py` agora emite `LOCAL_SHARED_LIBRARIES` conforme `DT_NEEDED`.
Uma biblioteca selecionada com nome de módulo diferente do SONAME usa esse alias;
casos especiais podem ser definidos no objeto `dependency_modules` do plano
revisado, por exemplo `{"libstockfoo.so": "libstockfoo_compat"}`. Isso dá ao build
Android as dependências necessárias em vez de apenas copiar arquivos.

O gerador recusa substituir os módulos de fonte que possuem `rild`, `libril`,
áudio CAF, GPS comum e `libcommon_time_client` por cópias stock. No plano, essas
entradas precisam de `skip` e motivo; os blobs específicos de câmera/sensores
mantêm os nomes `*.vendor.msm8916.so` utilizados pelos wrappers.

O `vendor-audit.json` schema 2 registra hashes do inventário, plano revisado,
contratos e dos três makefiles gerados. Alterar um destino/módulo depois da
geração invalida os inputs de build. `ready_for_diagnostic_build` continua
significando somente seleção/formatos revisados, **não** ABI resolvida.

## Verificação das saídas reais antes de bacon

Depois de compilar os módulos e as imagens diagnósticas no builder maior:

```sh
python3 scripts/audit-native-dependencies.py \
  --product-out /builder/android/out/target/product/a7lte
python3 scripts/check-build-inputs.py --tree /builder/android \
  --layout /builder/stock-layout.json --require-native \
  --product-out /builder/android/out/target/product/a7lte \
  --native-report /builder/android/out/target/product/a7lte/native-dependencies.json
```

`audit-native-dependencies.py` analisa os ELFs efetivamente instalados em
`system/lib`, `system/vendor/lib`, `vendor/lib` e `bin` correspondentes. Confere
caminhos essenciais em `scripts/native-contracts.json`, cadeia `DT_NEEDED`, ABI
ARM32, provedores duplicados diferentes, shims injetados e símbolos dinâmicos
fortes não resolvidos. Importações fracas são opcionais; versões de símbolos são
preservadas. Bibliotecas com mesmo SONAME mas conteúdos diferentes são ambíguas:
o script não adivinha qual namespace o Android escolherá.

O relatório `native-dependencies.json` só tem `ready_for_image_packaging: true`
se essas verificações passarem. O gate de ZIP exige esse relatório; ao validá-lo,
recalcula todos os hashes e a auditoria, detectando arquivos alterados **ou novos
provedores ELF** adicionados desde a análise. A validação dos inputs continua
ativa com `PYTHONOPTIMIZE`, sem depender de instruções `assert` elimináveis.

Imagens diagnósticas podem continuar com layout/hashes verificados e pendências
explicitamente registradas; o alvo `bacon` não pode usar essa exceção para gerar
ZIP enquanto dependências essenciais não estiverem resolvidas. Relatórios vendor
schema 1 antigos não satisfazem o gate de ZIP.

Esse gate estático é necessário, mas não suficiente: namespaces de linker,
`dlopen`, HALs HIDL, offsets/semântica de structs, permissões e funcionamento no
aparelho permanecem fora da prova. `release_ready`, `device_tested`,
`linker_namespaces_verified` e `dlopen_behavior_verified` continuam falsos.

## Verificações novas executadas nesta etapa

Somente `tests/test_native_dependencies_new.py` foi executado: **12 casos novos
passaram**, com DSOs ARM32 reais, cobrindo closure, símbolos fortes/fracos,
shims, SONAME ambíguo, aliases de módulos, provedores adicionados, hashes
alterados, makefile adulterado e rejeição de substituição do `libril` de fonte.
Resultado: `logs/native-dependency-targeted-tests.log`.
Os 46 testes anteriores e o kernel não foram executados novamente.
