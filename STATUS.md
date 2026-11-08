# Estado atualizado — SM-A700FD / a7lte

O desenvolvimento foi continuado sem depender de espaço para o Android completo.
Base Samsung/Qualcomm Galaxy-MSM8916, LineageOS 16/Pie, com configuração A7 nativa.
Nenhum componente OPPO foi utilizado. Nenhum funcionamento no aparelho é declarado.

## Concluído e verificado

- Kernel original 3.10.108, zImage de 6.032.512 bytes, cinco DTBs e dt.img QCDT v2
  preservados byte por byte, junto aos patches e logs originais.
- Nova compilação real do mesmo kernel/config concluiu com saída 0. O resultado
  fresco permanece em out/kernel; o zImage original não foi substituído. Diferença
  de timestamp/host impede tratar o hash novo como idêntico ao build anterior.
- Árvore a7lte auditada: overlays Pie, herança e HAL Samsung de luzes, init
  modelo/device/DSDS, fstab montando system, firmware/EFS, recovery, GCC7.2,
  remoção de destinos duplicados e de tamanhos de partição inválidos.
- GNU Make avaliou o recorte de produto/BoardConfig: 66 destinos de cópia únicos.
  Regeneração reproduziu 196 arquivos. XML e sintaxe Python/shell passaram.
- Policy monolítica real compilada com `checkpolicy -M -c 30`, sem `-N`, mais
  checkfc Android 9 de contextos locais e combinados, todos saída 0. Patch Qualcomm
  restritivo elimina grants legados conflitantes; neverallows permanecem ativos.
- repo init/manifest real passou; sync de sete dependências pequenas passou.
  Revisions locais fixadas e replay standalone testado. Scripts para plataforma
  completa, overlay idempotente, kernel/policy/imagens/bacon e logs entregues.
- Extrator CSB1 e staging ZIP/TAR.MD5, auditoria ELF/NEEDED/símbolos, gerador vendor
  com plano revisado, parser PIT/boot e validação de hashes atuais implementados.
- 39 testes unittest integrados e 7 testes do downloader passaram (46 no total).
  Incluem DSOs ARM reais, arquivos ausentes/alterados, versões erradas, caminhos,
  symlinks, arquivos comprimidos e geometria sintética.
- Ferramentas locais simg2img/img2simg/lz4/debugfs/mke2fs obtidas com URLs e hashes
  fixos. Fixture real de 16 MiB: ext4↔sparse e LZ4 com hashes idênticos, extração
  debugfs somente leitura e origem inalterada.

## O que continua bloqueado

1. **Firmware exato real:** os índices SamFW/SamFrew estão acessíveis e identificam
   AP A700FDXXS1CSB1, CSC A700FDZTO1CSB1 e CP A700FDXXU1CPF1. SamFrew publica um
   ZIP alternativo de 1.454.404.384 bytes/MD5 próprio. Os fluxos de download
   observados exigem verificação; o cliente FUS legado falhou na leitura de nonce.
   Nenhum arquivo stock foi baixado ou autenticado. Há downloader verificável
   para URL direta autorizada e instruções para arquivo adquirido legitimamente.
2. **Stock/PIT/ABI:** faltam SYSTEM, boot/recovery e PIT reais para gerar layout e
   vendor. 77 entradas comuns não coincidem com a lista A7 histórica; não foram
   preenchidas com blobs de outros dispositivos. Símbolos Pie, HALs completos,
   NFC PN547 e ANT ainda precisam de validação com stock/build integral.
3. **Build Android completo:** não foi sincronizado/compilado neste disco. Scripts
   estão preparados para volume adequado, com snapshot resolvido após o primeiro
   sync completo. Ainda faltam lunch/Ninja, recursos/VINTF, linkagem HAL e policy
   split/CIL/imagens reais. O Containerfile foi preparado, não construído aqui.
4. **Aparelho:** não há testes de boot, rádio/dual SIM, câmera, áudio, sensores,
   energia, recuperação ou enforcing. Boot permanece permissive para bring-up;
   policy compilar não comprova permissões corretas nem funcionamento.

Detalhes e evidências em docs/ e logs/continuation/. O pacote atualizado contém
as árvores, templates, scripts, patches, testes, locks e logs. O pacote inicial
`artifacts/a7lte-progress.tar.gz` foi preservado, sem sobrescrita.

## Continuação e estratégia GitHub Actions

Boot/recovery/PIT oficiais CSB1 foram recuperados via FUS e HTTPS Range normal,
com hashes e fonte registrados; SYSTEM e os blobs CSB1 ainda não foram extraídos.
Foram adicionados contratos HAL, auditoria ELF real histórica, policy/source
corrections, layout stock parcial e QCDTv3 candidato separado. Artefatos originais
permanecem preservados. As tentativas locais de bootimage foram interrompidas
na mudança de estratégia; nenhum boot Lineage Android9 foi gerado.

A configuração final solicitada está em `.github/workflows/build_rom.yml`:
runner ubuntu22.04, limpeza descartável, sync raso, blobs de dispositivo/blobs,
serviços sem isolamento, ALLOW_MISSING_DEPENDENCIES=true e brunch direto.
Não há gate prévio para criação/upload do ZIP; ocorre fallback bootimage se o
brunch falhar. O workflow foi validado estaticamente, não executado no GitHub.
Veja docs/github-actions.md e logs/ci-validation. Nenhuma imagem foi testada no A7.
