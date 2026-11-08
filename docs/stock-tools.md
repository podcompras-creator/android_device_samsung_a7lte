# Ferramentas locais para imagens stock

As ferramentas agora estão disponíveis no workspace, separadas dos compiladores
e do `bc`, `m4` e `checkpolicy` existentes. Não é necessário sudo nem montagem.
Os pacotes oficiais Debian ficam em `host-packages/stock-tools/`; extração local
em `host/stock-tools/`, com wrappers que configuram bibliotecas e `mke2fs.conf`.

```sh
python3 scripts/fetch-stock-tools.py
# Ou reproduzir sem rede, verificando os pacotes já baixados:
python3 scripts/fetch-stock-tools.py --offline
export PATH="$PWD/host/stock-tools/bin:$PATH"
python3 scripts/test-stock-tools.py
```

`host-tools.lock.json` fixa URLs HTTPS, tamanhos e SHA-256 dos oito pacotes. O
bootstrap verifica o hash antes da extração. Total de downloads: aproximadamente
1 MiB; os arquivos locais não ocupam mais que alguns MiB. É necessário host Linux
x86_64, `dpkg-deb` e bibliotecas de runtime enumeradas no lock (glibc compatível,
libstdc++, zlib, libcom_err, libuuid, libblkid, liblz4 e libxxhash). O ambiente
Debian 13 atual atende a esses requisitos. O bootstrap não instala os pacotes no
sistema e não executa scripts maintainer; disponibiliza somente os binários e
bibliotecas necessárias. Não altera `host/usr/bin` nem `host/bin/dtbTool`.

Disponíveis: `simg2img`, `img2simg`, `lz4`, `debugfs`, `mke2fs`, `mkfs.ext4`.
O teste real produziu uma imagem ext4 **sintética** de 16 MiB, converteu para
Android sparse e de volta com SHA-256 idêntico, comprimiu/descomprimiu LZ4 legacy,
e extraiu `build.prop` usando `debugfs rdump` em modo somente leitura. Conferiu
conteúdo e que o SHA-256 da imagem original não mudou. Resultado em
`logs/stock-tools-fixture.json`; versões em `logs/stock-tools-bootstrap.log`.
Isso valida as ferramentas e a conversão nesta máquina, sem reivindicar teste
contra o pacote Samsung CSB1 que ainda não foi obtido.

Para usar o extrator stock entregue pelo projeto, mantenha esse diretório no
`PATH`. Execute sempre sobre arquivos de imagem, nunca sobre dispositivos de
bloco. A extração não precisa montar o filesystem nem alterar o conteúdo stock.
