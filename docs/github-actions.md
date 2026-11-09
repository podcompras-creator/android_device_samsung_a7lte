# Build no GitHub Actions

Workflow: `.github/workflows/build_rom.yml`; manifesto: `local_manifests.xml`.
A versão final solicitada executa `brunch a7lte` diretamente com
`ALLOW_MISSING_DEPENDENCIES=true`, sem auditoria de prontidão como gate do ZIP.
Se o build falhar, tenta `mka bootimage`; os uploads e logs são coletados mesmo
quando o job falha. Só são enviados ZIPs e boot.img existentes no PRODUCT_OUT
real, nunca fixtures NONFLASHABLE nem boot stock como saída Lineage.

O manifesto contém marcadores para o repositório publicado do port e seu commit;
o próprio workflow substitui-os por GITHUB_REPOSITORY e GITHUB_SHA antes do sync.
O transporte repo baixa o port em `.a7lte-port`; `apply-overlay.py` instala a árvore
nativa e os patches comuns. Os patches opcionais de isolamento foram retirados
da integração ativa. As declarações de audioserver/cameraserver/ril permanecem
normais. Nenhum serviço foi duplicado no init.

Se houver `dispositivo/blobs`, ele precisa conter a estrutura vendor Samsung A7
(`Android.mk`, `a7lte-vendor.mk`, `BoardConfigVendor.mk`, `proprietary/`). Caso
contrário, o runner adquire o SYSTEM CSB1 oficial e gera o vendor com os arquivos
reais encontrados. O arquivo `a7lte-progress.tar.gz` enviado no chat foi conferido:
é o pacote de progresso anterior, sem bibliotecas `.so`, e não fornece esse vendor.
Os15ELFs comunitários históricos são referências2016, não substitutos.
Não são criadas bibliotecas ou arquivos vendor vazios para preencher faltas.

`ALLOW_MISSING_DEPENDENCIES` não resolve símbolos incompatíveis, caminhos de
makefiles inexistentes, falta de espaço ou problemas de execução no aparelho.
A limpeza é restrita a runner GitHub-hosted ubuntu22.04 descartável e não garante
80GiB livres nem capacidade para uma compilação Android completa. Os originais
no workspace local não são apagados. A flag foi habilitada por decisão explícita
do operador para tentativa de bring-up, sem implicar validação de ROM.

O workflow foi publicado em `podcompras-creator/android_device_samsung_a7lte` e
executado no GitHub Actions. A segunda execução,42513339588, adquiriu o AP oficial
com CRC ZIP e MD5 TAR válidos e converteu SYSTEM, mas parou em uma propriedade
Dalvik duplicada. O parser foi corrigido para aceitar overrides comuns e ainda
rejeitar conflitos de identidade. A execução42514831793 usa essa correção.
Os resultados de cada execução ficam em `logs/build-launch`; uma etapa ainda
pendente não é apresentada como compilação aprovada.

Para disparo pela integração GitHub, um commit em ci/build-trigger.json no main
inicia o mesmo workflow; workflow_dispatch também permanece disponível.

## Aquisição oficial quando o pacote local não contém blobs

A atualização do runner obtém SYSTEM diretamente do FUS Samsung para o CSB1
exato quando `dispositivo/blobs` estiver ausente. Essa aquisição ocorre antes do
sync da plataforma, valida o AP completo e a identidade de SYSTEM, gera o vendor
com hashes e remove apenas intermediários grandes criados pelo próprio job.
Não usa o pacote de progresso como se contivesse bibliotecas proprietárias.

O modo forçado solicitado permanece: `ALLOW_MISSING_DEPENDENCIES=true`, serviços
normais e brunch sem gate de ZIP. Arquivos ausentes no CSB1 são registrados como
pendências explícitas, sem substituição por arquivos2016 ou de outro modelo.
Compilar nesse modo não demonstra compatibilidade ABI nem boot no aparelho.

A limpeza inclui `/iossd`. O manifesto exclui somente o emulador e prebuilts
Darwin que não são utilizados pelo build Linux A7. O sync mantém2GiB de reserva
para o runner finalizar e enviar logs; se esse limiar for atingido, o erro é
registrado como insuficiência de disco, sem chamar a interrupção de erro Ninja.

O build expõe Python2 como `python` por um diretório temporário exclusivo da
etapa, pois `build/make/tools/findleaves.py` do Android9 usa sintaxe Python2.
Os scripts de aquisição continuam invocando `python3` explicitamente.
O vendor íntegro gerado é preservado em cache e também em um artefato separado,
`a7lte-csb1-vendor-N`, para auditoria dos bytes e metadados reais. Esse artefato
nunca representa uma ROM instalável.

Na integração, depois de `repo sync` e `apply-overlay.py`, o workflow usa `sed`
para corrigir `phone-xxhdpi-2048-dalvik-heap.mk` para o perfil Pie existente
`phone-xhdpi-2048-dalvik-heap.mk` em `device/samsung/qcom-common/qcom-common.mk`
e no `device.mk` aplicado. Confere antes a existência do destino e rejeita uma
referência antiga remanescente. O perfil configura o heap para2GiB de RAM;
a densidade de tela480dpi permanece independente. A verificação é registrada
em `logs/dalvik-heap-integration.log` antes de `brunch`.
