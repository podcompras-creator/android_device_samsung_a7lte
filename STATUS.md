# Estado atual — LineageOS 16 / SM-A700FD a7lte

Base Samsung/Qualcomm Galaxy-MSM8916, userspace ARM32. Nenhum componente OPPO
foi utilizado. Nenhuma gravação nem teste de inicialização no aparelho ocorreu.

## Resultado real mais recente

O projeto foi publicado em
https://github.com/podcompras-creator/android_device_samsung_a7lte . A plataforma
LineageOS16 foi sincronizada por completo no GitHub Actions. O runner observado
possui16GiB de RAM; havia61GiB livres antes do build da execução42541519000.
O disco local de aproximadamente8GiB não é usado para compilar o Android inteiro.

A execução42639113395 (tentativa7) passou no target nativo sepolicy_tests e
avançou até65196/74939etapas. Parou ao assinar WebView: o arquivo de entrada
era um ponteiro Git LFS de texto, gerando zip END header not found. Não houve
esgotamento de RAM ou disco:32GiB ainda livres no final. Não há ROM ZIP gerada.
Logs: logs/build-launch/actions-run7, incluindo as últimas50linhas reais.

O fallback bootimage terminou com saída0:8894480bytes,
SHA256 f51ff79947cebf236d5eac3bde198b834eab1c71d391ceea16056a7b552d44f7.
A verificação estrutural passou com os offsets CSB1corrigidos; o resultado
global permanece PARTIAL, sem SYSTEM nem ROM e sem teste físico.
O boot anterior da tentativa6 permanece preservado em
artifacts/android-run6-unvalidated, com seus offsets incorretos documentados.

A correção atual instala git-lfs e materializa os arquivos de entrada reais
antes de compilar, verificando SHA256/tamanho do ponteiro versionado, CRC ZIP
e JNI ELF32 ARM do WebView. O endpoint oficial respondeu com o objeto esperado
de90257078bytes; a sonda verificou somente identidade e primeiros bytes.
O download completo será conferido no runner. Dez testes direcionados passaram,
incluindo hash errado, CRC, arquitetura, JNI, compressão incompatível e disco.
Os46testes antigos não foram repetidos.

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

- Android completo, imagens finais e empacotamento: dependem da próxima
  execução com o APK WebView real. A tentativa7 confirmou as correções nativas
  de política e offsets; a correção Git LFS ainda precisa passar no runner.
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
