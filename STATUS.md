# Estado atual — LineageOS 16 / SM-A700FD a7lte

Base Samsung/Qualcomm Galaxy-MSM8916, userspace ARM32. Nenhum componente OPPO
foi utilizado. Nenhuma gravação nem teste de inicialização no aparelho ocorreu.

## Resultado real mais recente

O projeto foi publicado em
https://github.com/podcompras-creator/android_device_samsung_a7lte . A plataforma
LineageOS16 foi sincronizada por completo no GitHub Actions. O runner observado
possui16GiB de RAM; havia61GiB livres antes do build da execução42541519000.
O disco local de aproximadamente8GiB não é usado para compilar o Android inteiro.

A execução42720944356 (tentativa8) concluiu a compilação completa com saída0:
74939/74939etapas, build bacon, duração36:51. sepolicy_tests nativo passou.
O ZIP real lineage-16.0-20261109-UNOFFICIAL-a7lte.zip tem460017403bytes,
SHA256 65417a09052167303ba7cd275fe136e253b9555874b7f39882db9f73e9cbf488.
A validação estática nativa passou: CRC, OTA BLOCK/API28/a7lte, boot incorporado
igual ao boot independente, cabeçalhos Samsung e limites de partições.
Boot:8898576bytes, SHA256 c51e6b0ed903dbd4a990cb096c15d1598f8aaebf19e97744aa9d672ac90e6164.
Recovery:11874320bytes validado no runner; não enviado como arquivo separado.
Logs completos compactados e últimas50linhas: logs/build-launch/actions-run8.

A causa da tentativa7 foi resolvida: webview.apk era um ponteiro Git LFS.
A nova etapa materializou o APK oficial no runner e conferiu SHA256, tamanho,
CRC das620entradas e JNI ELF32 ARM. Dez testes direcionados passaram.
O APK oficial declara minSdkVersion26, compatível como requisito mínimo com
API28. Os46testes antigos não foram repetidos, e não houve build local.

O runner terminou com apenas1.6GiB livres, apesar de completar. O artefato
combinado guarda duas cópias idênticas do ZIP e soma927448663bytes, acima do
limite512MiB do conector. Um workflow de entrega separa os arquivos existentes
com conferência dos hashes, sem compilar, alterar imagens nem reassinar a ROM.
Artefato original preservado:
https://github.com/podcompras-creator/android_device_samsung_a7lte/actions/runs/42720944356/artifacts/13723127389 .

A inspeção do ramdisk real da tentativa7 confirmou init.target, init.qcom,
fstab e ueventd idênticos às fontes atuais. A referência ausente init.carrier.rc
é um aviso legado não fatal segundo o código Pie fixado; nenhum arquivo stock
foi copiado para preenchê-la. As imagens anteriores e os pacotes permanecem
preservados, inclusive o boot da tentativa6 com seus offsets errados documentados.

Nenhum boot nem teste de HAL ocorreu no aparelho. O sucesso da compilação e
as verificações estáticas não tornam este ZIP uma ROM funcional ou certificada
para instalação. As incompatibilidades conhecidas de GPS/RIL continuam abaixo.

## Concluído nesta integração

- Aquisição completa do AP CSB1 oficial via Samsung FUS normal: CRC da entrada
  ZIP e MD5 TAR conferidos; SYSTEM convertido e extraído sem executar firmware.
- Vendor CSB1 real preservado em cache e artefato:238arquivos selecionados na
  primeira geração e243na execução6, com todos os seis provedores novos reais;
  hashes dos arquivos e receitas conferidos localmente.
- Perfil Dalvik inexistente corrigido por sed após o sync. O destino Pie real
  phone-xhdpi-2048-dalvik-heap.mk é verificado antes do build.
- LINEAGE_BUILD permanece no ambiente pai; flags ARM e namespace Soong nativos
  confirmados no próprio JSON gerado pelo runner na execução42543011567.
- Marcador .find-ignore exclui módulos duplicados dos snapshots de .a7lte-port;
  verificado com o finder real do Pie e pelo avanço da compilação no runner.
- Wrapper de sensores corrigido: posse dos objetos, falhas de abertura,
  fechamento e reabertura; mock de ciclo de vida passou. Não valida hardware.
- Fonte Qualcomm fornece librmnetctl; regeneração dos237demais arquivos reais
  passou sem alterar os bytes de câmera. A lista agora tem263candidatos,
  incluindo seis provedores exigidos por DT_NEEDED dos blobs efetivos.
- Cache de compilação e métricas de RAM/disco preparados para as tentativas
  seguintes. O target nativo sepolicy_tests é compilado antes do restante do
  Android; o fallback bootimage permanece disponível se esse teste falhar.
- Cache depende também da lista de candidatos; a próxima aquisição guarda um
  catálogo de caminhos reais de SYSTEM, sem seguir links Android no host.
- Kernel, zImage, cinco DTBs, dt.img QCDTv2, QCDTv3 separado, patches e logs
  anteriores permanecem preservados. Os46testes antigos não foram repetidos
  nesta fase; as verificações novas estão em logs/build-launch e logs/csb1-abi.

## Pendências demonstradas

- A compilação completa e o ZIP estão concluídos. Permanecem as verificações
  físicas e de ABI/HAL abaixo; nenhuma aprovação para flash foi emitida.
- GPS: libloc_api_v02.so exige o objeto sec_gps_conf, ausente no fornecedor de
  fonte selecionado. O objeto existe no libgps.utils.so stock não instalado.
- RIL: o protobuf nativo3.0 usa assinatura de construtor incompatível com a
  importada pelo blob CSB1; precisa de ABI legada isolada, sem substituir o
  protobuf de toda a plataforma. A evidência está em
  logs/csb1-abi/actual-source-abi-audit.json.
- Permanecem duas ausências RenderScript registradas na seleção. Os seis
  provedores adicionais passaram na aquisição real; nenhuma biblioteca
  substituta ou placeholder foi criada.
- Testes no aparelho, funcionamento das HALs e SELinux enforcing continuam
  pendentes. Policy compilar e um ZIP ser gerado não demonstram boot funcional.

O modo diagnóstico explicitamente solicitado continua ativo:
ALLOW_MISSING_DEPENDENCIES=true, serviços normais e brunch a7lte, sem gate de ZIP.
Isso não corrige ABI nem certifica uma imagem para instalação.
O histórico anterior permanece nos commits e logs; os pacotes originais não
foram sobrescritos. Fontes, auditorias e scripts atuais estão versionados.
