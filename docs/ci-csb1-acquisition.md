# Aquisição completa de SYSTEM no runner

`ci/fetch-csb1-system.py --output DIR` usa o FUS moderno já validado para
`SM-A700FD`, ZTO, versão
`A700FDXXS1CSB1/A700FDZTO1CSB1/A700FDXXU1CPF1/A700FDXXS1CSB1`.
O diretório precisa ser novo ou vazio. O script exige **9 GiB livres antes de
qualquer rede** e `openssl`, `simg2img`, `debugfs` e Python3 no runner.
O teto de transferência por execução é **3 GiB**, autenticado normalmente no
serviço Samsung; não usa CAPTCHA, identificador inventado ou blob OPPO.

O ZIP cifrado oficial é lido por ranges através do cliente MIT existente.
Somente o TAR AP identificado nos metadados FUS é processado. SYSTEM sparse,
boot e recovery são gravados em `.work-system/`; os demais membros são consumidos
sem gravação. O leitor **consome toda a entrada ZIP AP até EOF**, fazendo o
`zipfile` conferir o CRC da entrada; registra SHA-256 e tamanho completos do TAR
e confere seu footer Samsung MD5 quando presente. Não alega verificar o CRC do
ZIP cifrado inteiro, as outras entradas BL/CP/CSC ou assinatura Samsung.

Depois da integridade AP, `simg2img` converte todo SYSTEM e a geometria ext4 é
conferida. `debugfs rdump` extrai o filesystem completo em modo somente leitura,
sem montagem ou execução de arquivos stock. O validador existente exige model,
manufacturer Samsung, dispositivo a7lte e PDA/incremental CSB1 exatos.
**`DIR/system` só aparece após essas etapas passarem**. Em seguida boot/recovery
são publicados e somente os intermediários grandes criados pelo próprio script
são removidos.

Saídas aceitas pelo adaptador de blobs:

- `DIR/system/build.prop` e demais arquivos SYSTEM completos;
- `DIR/boot.img`, `DIR/recovery.img`;
- `DIR/fetch-result.json`, com `success:true`, `metadata`, `ap_archive`,
  `selected_payloads`, `raw_system`, `system_identity` e ranges/hashes de origem;
- `DIR/fus-metadata/`, logs de conversão e extração.
- `DIR/system-file-catalog.json`, com caminhos, tipos, tamanhos regulares e
  destinos de links do SYSTEM real; links externos não são seguidos no host.

Qualquer falha escreve `success:false` e não publica `DIR/system`; dados de
trabalho e logs ficam disponíveis para diagnóstico. A validação dos257 blobs,
ABI/DT_NEEDED, dependências e geração vendor continua sendo feita separadamente
pelo adaptador CI, sem transformar arquivos ausentes em placeholders.

Validação local desta mudança: **sete testes direcionados**, incluindo EOF/CRC
no footer, MD5 TAR incorreto, stream truncado, caminhos inseguros/duplicados,
guarda de espaço antes da rede e conversão/rdump real de ext4 **sintético**.
Nenhum SYSTEM stock completo foi baixado no ambiente local de~500MiB livres.
Na execução42514831793, a aquisição completa e a geração vendor passaram no
runner. A execução42541519000 restaurou esse vendor e o publicou como artefato.
O catálogo de caminhos é uma adição posterior, que será registrado na próxima
aquisição completa; seu teste local só usou metadados de filesystem sintético.
