# LineageOS 16 / Android 9 — Samsung SM-A700FD (a7lte, MSM8939)

Desenvolvimento nativo baseado em Galaxy-MSM8916 e referências Samsung A7.
Nenhum componente OPPO foi utilizado. O projeto continua em desenvolvimento;
a ROM completa e o funcionamento no aparelho ainda não foram demonstrados.

- `STATUS.md`: resultados atuais e bloqueios concretos.
- `android/device/samsung/`: árvores prontas para aplicar à plataforma.
- `templates/`: overrides auditados e reproduzíveis; referências em `sources.lock.json`.
- `patches/`: alterações do kernel, comum Samsung e policy Qualcomm.
- `artifacts/`: kernel/zImage, cinco DTBs, dt.img, config, símbolos e hashes preservados.
- `logs/`: builds reais, auditorias, falhas anteriores e testes.
- `scripts/`: preparação, sync/build, firmware, extração, revisão vendor e layout.

O kernel original deste trabalho compilou com saída 0 e gerou zImage ARM de
6.032.512 bytes. `dt.img` QCDT v2 contém cinco DTBs Samsung A7 EUR e 15 entradas,
com validação estrutural aprovada. A preservação por hash está registrada em
`logs/continuation/`. Esses artefatos não são imagens prontas para flash.

## Como continuar

Leia [Build completo](docs/build.md). Os scripts fazem repo init/sync, verificam
as dependências, aplicam os patches e executam lunch/make em um volume maior.
Checagens de fonte, ferramentas, policy e componentes continuam possíveis aqui.

A aquisição/extração stock e a auditoria dos blobs estão em
[Fontes de firmware](docs/firmware-sources.md), [Staging seguro](docs/unpack-stock.md),
[Blobs](docs/blobs.md), [Ferramentas stock](docs/stock-tools.md) e [PIT/boot](docs/partitions.md).
A árvore e as limitações de HALs estão em [Auditoria de dispositivo](docs/device-audit.md).
SELinux e seus resultados estão em [Auditoria de policy](docs/sepolicy-audit.md).

SamFW e SamFrew identificam a versão exata CSB1, com pacotes/checksums distintos;
não se confunde vendor comunitário de 2016 com firmware CSB1 de 2019. Ainda falta
obter e auditar os binários reais por um fluxo autorizado, executar o build
integral e testar no SM-A700FD. Nenhum ZIP funcional é declarado nesta entrega.
