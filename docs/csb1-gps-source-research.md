# Pesquisa da extensão Samsung GPS exigida pelo CSB1

Pesquisa somente leitura em8denovembrode2026 (America/Sao_Paulo). Nenhuma configuração de outro aparelho,
stub, blob histórico ou componente OPPO foi incorporado à produção.

O relatório real `logs/csb1-abi/actual-source-abi-audit.json` identifica
`libloc_api_v02.so` exigindo **OBJECT GLOBAL sec_gps_conf**. O provider stock CSB1
`libgps.utils.so` de46.964 bytes tem SHA-256
`41212684637073b506b03aa8f205c95628224e61d3116e7a423969adc1e441c1`.
A implementação pública escolhida de GPS utils não fornece a extensão Samsung.

## Fontes Galaxy-MSM8916 comparadas

`gps/utils/loc_cfg.h` e `loc_cfg.cpp` foram consultados nestas revisões:

| Branch | Commit |
| --- | --- |
| cm-13.0 | `c3f237234ce046a390bfaf10b9163f39268c4dc8` |
| cm-14.1 | `a4605b0fe5d029513a0af23d5d09bd45fe0364b9` |
| lineage-15.1 | `1df417e595b4f67bb7bffc4d38eaec97e941f4a8` |
| lineage-16.0 | `7f8723dc42663bf09d085d9c19ecaa2b28617241` |

Nenhum desses arquivos define `sec_gps_conf`, `Sec_Configuration` ou funções
`loc_secgps`. O tree público cm13 também foi inspecionado, assim como a árvore
A7 original. Snapshots, hashes, referências e consultas estão em
`logs/csb1-abi/gps-source-research/`; resumo verificável em `source-audit.json`.
As buscas públicas exatas por `loc_read_sec_gps_conf`,
`loc_secgps_default_parameters`, `loc_secgps_get_params_table` e
`sec_gps_cfg_s_type` não localizaram implementações reais nos índices consultados.
Isso descreve o alcance da pesquisa; não prova inexistência em todos os fontes.

## Resultados enganosos explicitamente rejeitados

No fork Samsung/MSM8916 **Chemnitzer**, commit
`cb5aaa629f94f1521aec042bd263a3b8ab9364ab`, o próprio título é
“gps: Add dummy functions stubs”. O patch cria:

```c
/* Observado no patch histórico, NÃO uma definição legítima CSB1. */
typedef struct { char OPERATION_MODE[50]; } sec_gps_cfg_s_type;
typedef struct { char STUB[50]; } Sec_Configuration_s_type;
```

Essas estruturas de50 bytes são stubs declarados e não fornecem o layout completo,
defaults ou parser Samsung. A procedência de um fork MSM8916, isoladamente, não
as torna compatíveis com CSB1. Não foram copiadas.

Outro resultado em `CyanogenMod/android_device_samsung_d2-common`, cm14.1,
`gps/utils/sec_gps.c`, define **funções** `int sec_gps_conf(void)` e
`int Sec_Configuration(void)` retornando zero. O símbolo exigido pelo consumidor
CSB1 é um **objeto**, portanto esse resultado tem inclusive tipo ABI incorreto.
Não foi reutilizado.

## Comparação histórica genuína A7

O provider histórico A7 já presente no workspace tem o mesmo tamanho46.964 bytes,
mas SHA-256 distinto:
`37a59901efd1a9b001d5fdfc90d6b4060c84a6cc71fbd672185cbab201114e8a`.
Sua tabela ELF mostra `sec_gps_conf` como **OBJECT148 bytes**,
`Sec_Configuration` como **OBJECT4 bytes** e `loc_secgps_param_num` como
**OBJECT4 bytes**, além das funções Samsung citadas. O relatório completo está
em `historical-a7-gps-symbols.txt`. Os tamanhos são observações desse binário
histórico; não se inventou um typedef CSB1 a partir deles nem se assumiu que
binários de mesmo tamanho têm comportamento idêntico.

## Resultado e próximo limite técnico

**Não foi localizada uma definição pública exata e comprovada da estrutura e
comportamento Samsung CSB1 nesta pesquisa.** Exportar uma variável zerada,
reservar148 bytes ou copiar um stub de50 bytes faria apenas o linker aceitar o
nome, sem implementar a configuração esperada. A solução precisa de fonte real
correspondente ou de um conjunto privado coerente de bibliotecas **CSB1 genuínas**,
com toda a ligação e compatibilidade ABI verificadas. Esta pesquisa não autoriza
nem declara testada essa solução; apenas elimina os stubs inadequados encontrados.
