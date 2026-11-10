# Entrega real da tentativa8

Build completo: run42720944356, checkout1f2b06c7b1d5d91cba8ae58bcf996aaf4916da72, correçãoGitLFS85cd89dfc5d6e17a4ba24396bcc8ec86ba42c934. sepolicy_tests0, brunch0,74939/74939,36:51. Nenhum teste no aparelho.

ROM: lineage-16.0-20261109-UNOFFICIAL-a7lte.zip,460017403bytes, SHA25665417a09052167303ba7cd275fe136e253b9555874b7f39882db9f73e9cbf488.

Download: https://github.com/podcompras-creator/android_device_samsung_a7lte/actions/runs/42728375093/artifacts/13723233150

Boot real:8898576bytes, SHA256c51e6b0ed903dbd4a990cb096c15d1598f8aaebf19e97744aa9d672ac90e6164. Preservado localmente sem alterações.

Downloadboot: https://github.com/podcompras-creator/android_device_samsung_a7lte/actions/runs/42728375093/artifacts/13722588646

O workflowdeentrega somente copiou os arquivos anteriores após conferir hashes; não compilou, editou imagens nem reassinou a ROM. Os links são artefatos GitHub retidos até24/11/2026 e incluem checksums específicos. O artefato original duplicado permanece preservado.

Validação independente: artefato único baixado integralmente em RAM; SHA256 externo e interno, CRCs, metadata a7lte/API28/BLOCK e boot Samsung passaram. O ZIPde460MB não foi salvo no disco local limitado. Logs e verificações em logs/build-launch/actions-run8 e actions-run8-delivered-rom-verification.json.

Recovery11874320bytes passou na validação no runner, mas o workflow original não preservou seu arquivo separado; somente o relatório está disponível.

Conhecidas pendências: sec_gps_conf no GPS, ABI protobuf do RIL, duas ausências RenderScript, testes físicos de boot/HAL e SELinux enforcing. ALLOW_MISSING_DEPENDENCIES continuou ativo conforme solicitado. O protótipo privado de protobuf permanece fora do vendor e da ROM. Não houve componenteOPPO, arquivo arbitrário de substituição ou gravação no aparelho. Esta entrega não certifica instalação ou funcionamento.

O pacote consolidado é de fontes/progresso, não um ZIPdeinstalação. Inclui artefatos antigos reais e fixtures previamente marcadas NONFLASHABLE em pastas próprias. Os pacotes anteriores não foram sobrescritos.

Pacote compacto atual: a7lte-run8-core-progress.tar.xz. Inclui fontes atuais, scripts, patches, logs, zImage original, cinco DTBs, dt.img e boot real da tentativa8. O ELF de debug vmlinux, fixtures NONFLASHABLE e imagens antigas não são duplicados nele. Todos permanecem intactos no workspace e no pacote completo anterior a7lte-run8-sources-progress.tar.gz (SHA256 b543db611eee8c72a6dfc14ad4e35f50d2de279f12c48209f8b62ad09b0dae35). Os catálogos históricos de hashes referem-se aos respectivos conjuntos; RUN8-SHA256SUMS cobre os binários principais atuais.
