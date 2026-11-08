# Firmware exato A700FDXXS1CSB1 — fontes e resultado das consultas

Pesquisa inicial em 2026-11-07; avanço oficial confirmado em 2026-11-08, usando HTTPS com verificação TLS. Nenhuma imagem OPPO,
firmware de outro modelo ou blob sem identificação foi incorporado.
Os resultados iniciais estão em `logs/firmware-research/`; evidências oficiais novas
em `logs/phase3-firmware/`.

## Identidade encontrada

Dois índices independentes de terceiros confirmam SM-A700FD, região ZTO,
AP `A700FDXXS1CSB1`, CSC `A700FDZTO1CSB1` e Android **6.0.1**.
A página e listagem de arquivos SamFrew também informam modem `A700FDXXU1CPF1`,
changelist `9442021`, compilação de 2019-02-11 e upload de 2019-03-19.
Esses valores vêm dos índices; ainda não foram conferidos no `build.prop`, PIT,
cabeçalhos de boot ou ELF extraídos de um pacote stock baixado.

| Fonte | Resultado observado | Utilidade e limite |
| --- | --- | --- |
| [SamFW exato](https://samfw.com/firmware/SM-A700FD/ZTO/A700FDXXS1CSB1) | HTTP 200 nesta retomada; o 403 anterior não é mais o resultado atual | Página descreve pacote de 1,8 GB e MD5 `9e0832c89ff36ad18f494ee5b8777a64`. A ação de download exige Cloudflare Turnstile. Não foi contornado. |
| [SamFrew exato](https://samfrew.com/download/Galaxy__A7__/kucw/ZTO/A700FDXXS1CSB1/A700FDZTO1CSB1) | HTTP 200, firmware e CSC exatos | Alternativa concreta ao SamFW, com listagem pública de conteúdo abaixo. O fluxo Standard Download anuncia verificação. |
| [SamFrew arquivos](https://samfrew.com/files/zf493a399a400/SM-A700FD_1_20190309000427_inzulpmz4j.zip) | HTTP 200, nome, tamanho e MD5 publicados | ZIP `SM-A700FD_1_20190309000427_inzulpmz4j.zip`, **1.454.404.384 bytes**, MD5 **`150c9a4b318c20cb6fe043ce7cccfaf4`**. Contém `A700FDXXS1CSB1_A700FDZTO1CSB1_A700FDXXU1CPF1_HOME.tar.md5`, tamanho anunciado **2.487.040.088 bytes**. Download individual do TAR está indisponível sem autorização/premium. |
| [Samsung FOTA](https://fota-cloud-dn.ospserver.net/firmware/ZTO/SM-A700FD/version.xml) | HTTP 403, Akamai Access Denied | Serviço oficial de metadados OTA; essa resposta não prova que a Samsung removeu o pacote. |
| [Samsung FUS](https://neofussvr.sslcs.cdngc.net/) | **API moderna: HTTP 200, Status S00 para CSB1 exato. Download autorizado: HTTPS Range 206.** | Cliente de metadados corrigido com implementação MIT Bifrost; componentes oficiais boot/recovery/PIT já obtidos. API legada retorna 408 sem identificador, mas a moderna não precisou de IMEI/serial. |
| [Samsung Open Source](https://opensource.samsung.com/uploadSearch?searchValue=SM-A700FD) | HTTP 200, zero resultados para o modelo exato | Repositório oficial de código aberto. Pacotes GPL, mesmo quando disponíveis, não substituem os HALs proprietários. |
| [SamMobile índice ZTO](https://www.sammobile.com/samsung/galaxy-a7/firmware/SM-A700FD/ZTO/) | HTTP 200 | Índice adicional consultado; não foi obtido link de binário exato, logo não é apresentado como download confirmado. |

**Não aplicar o MD5 de um espelho ao ZIP do outro.** Os tamanhos e MD5 diferem;
isso pode refletir empacotamentos distintos, mas não foi verificado. MD5 publicado
pelo espelho ajuda a detectar troca/corrupção do pacote; não autentica a autoria
Samsung. `SHA-256` do pacote efetivamente obtido será registrado pelo downloader.

## Ferramentas entregues

`python3 scripts/download-firmware.py sources` apresenta as fontes em JSON.
O script usa apenas a biblioteca padrão Python e mantém a verificação TLS.
O comando de download aceita um **URL HTTPS direto adquirido pelo fluxo normal
e autorizado do site**; não efetua login, resolve CAPTCHA, reutiliza cookies,
contorna planos premium nem tenta adivinhar URLs de arquivo.

```sh
# Exemplo para o ZIP SamFrew, depois de obter legitimamente o URL direto:
python3 scripts/download-firmware.py download firmware/samfrew-CSB1.zip \
  --url 'URL_HTTPS_DIRETO_OBTIDO_NO_SITE' \
  --expected-md5 150c9a4b318c20cb6fe043ce7cccfaf4

# Ou verificar um pacote local sem rede:
python3 scripts/download-firmware.py verify firmware/samfrew-CSB1.zip \
  --expected-md5 150c9a4b318c20cb6fe043ce7cccfaf4

python3 scripts/test-download-firmware.py
```

O downloader recusa HTML/JSON, hash divergente, destino já existente, caminho ZIP
inseguro, arquivo que não identifica AP+CSC exatos, tamanho excessivo e falta de
espaço. Escreve `.part`, confere tamanho/hash e diretório ZIP, e só então publica
ZIP e inventário. Não extrai os arquivos do ZIP automaticamente. Arquivos parciais
são preservados para diagnóstico; uma tentativa nova exige outro destino ou
revisão explícita do parcial pelo operador. O inventário indica o alcance da
validação: não substitui a conferência do conteúdo pelo extrator stock.

## Rota oficial Samsung confirmada nesta fase

A falha anterior foi diagnosticada: o decoder AES legado do samloader arquivado
produzia padding inválido e nonce vazio. A implementação MIT atual do
[Bifrost/SamloaderKotlin](https://github.com/zacharee/SamloaderKotlin), revisão
`ed73a034d3b27d84c68b2c21622a9de6618455de`, autentica o bloco bruto do nonce
usando `auth_param.dat`. Foi portada para Python, preservando licença e hashes
em `tooling/fus-auth/`. Isso executa a autenticação normal do protocolo FUS;
não resolve CAPTCHA nem ignora exigências do servidor.

```sh
# Consulta somente metadados, com diretório de saída novo:
python3 scripts/query-samsung-fus.py --output /tmp/a7lte-fus-query

# Obtém boot/recovery/PIT por ranges, limitado a150MiB:
python3 scripts/fetch-fus-stock-components.py --output /tmp/a7lte-stock-components
python3 tests/test_fus_metadata.py
```

Nenhum identificador pessoal foi usado, gerado ou registrado. A API moderna
`NF_SmartDownloadBinaryInform.do` retornou **S00**, confirmando:

```text
Modelo: SM-A700FD   Região: ZTO
Versão: A700FDXXS1CSB1/A700FDZTO1CSB1/A700FDXXU1CPF1/A700FDXXS1CSB1
Pacote: SM-A700FD_1_20190319093540_yipiin0bmb_fac.zip.enc4
Tamanho cifrado: 1.935.783.696 bytes
CRC32 cifrado informado pelo Samsung FUS: 1404645705
```

Após `NF_SmartDownloadBinaryInitForMass.do` aprovado, requisições HTTPS Range
à distribuição oficial `cloud-neofussvr.samsungmobile.com` retornaram **206**,
com limites e tamanho total conferidos. O ZIP cifrado permite leitura por blocos
AES-ECB, assim foi possível ler o diretório ZIP e apenas o início dos TARs AP e
CSC, sem baixar SYSTEM nem o pacote completo. Transferência nessa extração:
**23.181.072 bytes**.

Componentes completos obtidos em
`logs/phase3-firmware/official-components-20261108/`:

| Componente | Bytes | SHA-256 |
| --- | ---: | --- |
| `boot.img` | 11.895.056 | `01e1ff5ad1d1530cb922ae884f6796794e3dadae620341107fd5ebc993e27e12` |
| `recovery.img` | 13.490.448 | `ff6668d81c6dd5b29762858609f68bca83afe2d8eef26ad0b75f83d19df5f82c` |
| `A7LTE_EUR_OPEN.pit` | 4.376 | `efab84121a4b5a9d45a9f860225336f1a8386a75240bb2d46ad11e0061a52b11` |

Os dados vieram do pacote oficial exato, por TLS e autenticação FUS. Cada imagem
foi recuperada integralmente e tem hash registrado. **O CRC do ZIP inteiro e os
footers MD5 dos TARs completos não foram verificados**, pois a transferência foi
parcial. A inspeção dos cabeçalhos/ramdisks/PIT é uma verificação adicional,
e não se deve descrever a transferência parcial como validação criptográfica
integral do firmware. Os arquivos recebidos não foram executados nem gravados
em aparelho. APIs legadas retornam408 nesta consulta; não foi inventado IMEI
nem procurado identificador de outro aparelho, porque a API moderna funcionou.

O script de componentes conserva o teto de transferência, confirma cada
`Content-Range`, identidade modelo/CSC/versão e autorização antes de ler. Os
intervalos cifrados e decifrados têm SHA-256 de evidência. O pacote e imagens
stock continuam sujeitos aos direitos da Samsung; nenhum componente OPPO foi
usado.

## Proveniência do vendor histórico

[MSM8939-Samsung/android_vendor_samsung_a7lte](https://github.com/MSM8939-Samsung/android_vendor_samsung_a7lte)
é mantido pela comunidade, apesar do nome conter Samsung. A API retornou head
`0f039d3c6c76b8fc9ece945f54a09056a09d9dcf` (o valor integral registrado no JSON
é a referência de máquina), com commits de 2016. Os históricos dizem
“Update blobs to Samsung Marshmallow Release” em junho de 2016; portanto, o
repositório **não prova origem na versão CSB1 de 2019**. Serve para estudar ABI,
nomes e lista candidata do A7; não foi usado para rotular blobs como CSB1 nem para
substituir silenciosamente o firmware solicitado.

## O que permanece bloqueado

A aquisição de **todo** o firmware deixou de depender dos espelhos: a Samsung
confirma e fornece o pacote exato por FUS moderno. Nesta fase foram obtidos os
componentes de boot e o PIT sem ocupar espaço para o ZIP completo. A aquisição
e validação de todo SYSTEM/vendor ainda precisam de espaço para o pacote cifrado,
ZIP decifrado e a extração, ou de um pipeline de extração seletiva que comprove
integralmente os blocos dos arquivos escolhidos. Blobs comunitários de2016 não
foram promovidos silenciosamente a CSB1. Nenhum teste de boot no SM-A700FD foi feito.

## Tentativa adicional de SYSTEM sem baixar tudo

Foi executado um probe limitado do começo de `system.img.ext4` dentro do AP.
O cabeçalho sparse oficial informa **642.560 blocos de4.096 bytes**, isto é,
**2.631.925.760 bytes** de filesystem lógico. Um arquivo ext4 incompleto,
esparso e apenas diagnóstico foi mantido em `/tmp/a7-csb1-incomplete-system.raw`.
O inode raiz2 foi lido, mas seu diretório aponta ao bloco **632.632**, perto do
fim do filesystem (~2,59GB). Assim, `/build.prop` não pode ser resolvido a partir
dos blocos iniciais; `debugfs` reportou diretório incompleto. Nenhum arquivo foi
extraído dessa imagem parcial nem aceito como blob verificado.

Essa tentativa transferiu mais **60.929.808 bytes**, antes de uma expiração401
da sessão FUS. Somando extração dos componentes e probe inicial de64KiB, o total
ficou em aproximadamente **84,2MB**, abaixo do teto150MiB. Evidência de blocos
cobertos, ranges e erro em `logs/phase3-firmware/system-prefix-20261108/`;
o código exato do probe está em `logs/phase3-firmware/system-prefix-probe.py`.
O leitor reutilizável de ranges recebeu renovação normal de autorização FUS
(uma nova consulta e BinaryInit para o **mesmo** pacote, uma tentativa), coberta
por teste direcionado. Não foi necessário contornar autenticação.

O campo físico do diretório raiz fica além do prefixo obtido. Como o AP é uma
entrada DEFLATE única no ZIP, chegar a esses dados exige descomprimir o fluxo
anterior ou possuir um índice de checkpoints verificado. Isso ainda não foi
feito dentro do teto de transferência e espaço desta sessão. O resultado não
é evidência de corrupção do firmware Samsung; somente da incompletude deliberada
do arquivo de diagnóstico. As imagens completas boot/recovery e PIT obtidas
anteriormente continuam preservadas e independentes desse probe.
