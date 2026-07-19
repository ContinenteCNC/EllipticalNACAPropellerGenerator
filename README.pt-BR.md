# Gerador de Hélices NACA Elípticas

[English](README.md) | [Português do Brasil](README.pt-BR.md)


Add-in multilíngue para Autodesk Fusion que gera hélices paramétricas
completas, com planta elíptica e transições suaves entre aerofólios NACA de
quatro dígitos.

Versão atual: **v1.1.1**

## Recursos

- Uma a doze pás, nos dois sentidos de rotação.
- Passo geométrico constante e sweep configurável.
- Distribuição de corda limitada por elipse.
- Perfis NACA independentes na raiz, região intermediária e ponta.
- Transições não lineares suaves e fairing configurável na raiz.
- Espessura física do bordo de fuga.
- Seções automáticas por espaçamento ou número de slices.
- Loft de superfície nativo do Fusion, trims radiais exatos e sólido B-Rep.
- Hub, furo do eixo, aro retangular, anel NACA aerodinâmico e spinner parabólico ou ogival.
- Interface em português, inglês, espanhol, francês, alemão e russo.
- Persistência automática e atômica dos parâmetros validados.
- A ação nativa **Gerar** encerra o comando após cada rodada confirmada.
- Configurações JSON distribuídas e criadas pelo usuário.
- Logs JSON detalhados para execuções manuais.
- Loft validado com bordo de fuga separado, Trim pré-Stitch e Boundary Fill.
- Janela compacta organizada em grupos recolhíveis, com progresso manual cancelável.

## Instalação

Copie a pasta completa `EllipticalNACAPropellerGenerator` para o diretório de
add-ins do Autodesk Fusion e reinicie o programa.

Windows:

```text
%appdata%\Autodesk\Autodesk Fusion\API\AddIns
```

macOS:

```text
~/Library/Application Support/Autodesk/Autodesk Fusion/API/AddIns
```

A pasta, o arquivo Python principal e o manifesto usam o mesmo nome:

```text
EllipticalNACAPropellerGenerator/
├── EllipticalNACAPropellerGenerator.py
└── EllipticalNACAPropellerGenerator.manifest
```

## Projeto original

A matemática das pás e dos spinners deriva de:

**Elliptical-blade NACA airfoil propeller library**  
Alex Matulich / Amatulic  
https://www.thingiverse.com/thing:5300828

O autor original explica detalhadamente a abordagem em:

https://www.nablu.com/2022/03/elliptical-blade-naca-airfoil-propeller.html

Consulte [ATTRIBUTION.md](ATTRIBUTION.md),
[UPSTREAM_LICENSE.txt](UPSTREAM_LICENSE.txt) e
[docs/SOURCE_LINEAGE.md](docs/SOURCE_LINEAGE.md).

## Alterações realizadas neste port

A biblioteca OpenSCAD original cria pás como poliedros facetados e fornece
módulos de spinner parabólico e ogival. Este projeto reimplementa as equações
em Python e acrescenta um fluxo completo para Autodesk Fusion:

- geometria B-Rep nativa e suave;
- interface gráfica multilíngue;
- presets em JSON;
- trim radial e verificação do sólido;
- padrão de pás, hub e furo do eixo;
- aro periférico opcional;
- montagem automática dos spinners.

Nos testes de sobreposição, os vértices do modelo OpenSCAD coincidiram ou
tangenciaram o loft do Fusion. Perfis, passo e sentido do sweep também foram
confirmados.

## Mapa do repositório

- `EllipticalNACAPropellerGenerator.py`: construção usando a API do Fusion.
- `propeller_math.py`: equações puras, sem dependência da API Autodesk.
- `localization.py` e `locales/`: localização da interface.
- `propeller_defaults.json`: padrões originais imutáveis.
- `configurations/`: configurações distribuídas; configurações do usuário ficam na pasta por usuário.
- `docs/GEOMETRY.md`: fórmulas e convenções de coordenadas.
- `docs/FUSION_API_PIPELINE.md`: sequência de construção B-Rep.
- `docs/LLM_CONTEXT.md`: contexto compacto para manutenção humana ou por LLM.
- `docs/ROADMAP.md`: desenvolvimento planejado após a v1.0.

## Licenciamento

O repositório combina uma implementação Python/Fusion original com geometria
e equações adaptadas. A licença MIT em [LICENSE](LICENSE) cobre apenas as
contribuições originais deste projeto. O material upstream mantém os requisitos
de atribuição Creative Commons. Leia também
[ATTRIBUTION.md](ATTRIBUTION.md) e
[UPSTREAM_LICENSE.txt](UPSTREAM_LICENSE.txt).


## Anel aerodinâmico NACA

A v0.20 transforma em recurso formal o anel com perfil de aerofólio mostrado
dentro do módulo `demo_random()` do projeto original do Thingiverse.

Por padrão, ele usa um NACA 0015, posiciona a linha de referência do bordo de
fuga no raio da ponta, orienta a corda no sentido axial e revoluciona o perfil
em 360 graus.

Parâmetros:

```text
Airfoil_Ring
Airfoil_Ring_NACA
Airfoil_Ring_Chord
Airfoil_Ring_Diameter
Airfoil_Ring_Axial_Offset
Airfoil_Ring_TE_Thickness
Airfoil_Ring_Profile_Points
```

`Airfoil_Ring_Chord = 0` usa a expressão automática original:

```text
min(20 mm, 0,5 * Propeller_Diameter * Max_Chord_Fraction)
```

O `Hoop` retangular existente continua disponível como recurso independente.


### Organização da interface

Os parâmetros estão agrupados por função. As famílias de anéis de ponta e
spinners usam uma única caixa de ativação e um seletor de tipo, evitando gerar
alternativas sobrepostas na mesma execução. Os nomes existentes no JSON
continuam compatíveis.


### Persistência automática dos parâmetros

Todos os parâmetros validados são salvos automaticamente ao pressionar
**Gerar**, antes de o Fusion iniciar a construção da geometria. Os valores
originais e imutáveis permanecem em `propeller_defaults.json`.

A última configuração gerada é armazenada fora do repositório e da pasta de
instalação do add-in:

```text
Windows: %APPDATA%\EllipticalNACAPropellerGenerator\propeller_user_config.json
macOS:   ~/Library/Application Support/EllipticalNACAPropellerGenerator/propeller_user_config.json
```

Ela volta quando o comando é aberto novamente, inclusive após reiniciar o
Fusion. Fechar a janela sem gerar não salva alterações que ainda não foram
executadas. A antiga ação de restaurar padrões foi convertida na configuração
incorporada **Hélice 3 × 1,25 pol. — configuração original**, de modo que todos
os pontos de partida são carregados pelo mesmo grupo Configurações.

### Geração, progresso e organização da linha do tempo

A versão 1.1 usa a ação nativa **Gerar** (OK) do Fusion. Uma rodada manual
concluída ou tratada encerra o comando, confirma sua transação única e só então
mostra o resultado. Para outra rodada, basta abrir o comando novamente; a última
configuração validada é restaurada automaticamente.

A geração manual mostra uma janela de progresso própria, cancelável, com a etapa
geométrica atual. O Automático robusto mantém sua janela independente de
legado/pesquisa. O cancelamento é cooperativo: uma operação longa do kernel do
Fusion termina antes que o próximo checkpoint consiga perceber o pedido.

Os checkpoints manuais chamam `adsk.doEvents()`, permitindo que viewport e linha
do tempo mostrem as features durante a criação. Uma candidata anterior não
processava esses eventos e atualizava principalmente no final; isso podia parecer
mais rápido por reduzir redesenhos, mas oferecia menos feedback. O texto do
progresso agora é quebrado em linhas de largura limitada para impedir que a
janela se expanda perto do fim.

Somente depois de confirmar a transação o add-in agrupa os novos itens da linha
do tempo, recolhe o grupo e usa nomes sequenciais:

```text
Elliptical NACA Propeller 01
Elliptical NACA Propeller 02
...
```

A mensagem final informa se o agrupamento funcionou, falhou ou foi ignorado. O
evento global `commandTerminated` cria o grupo somente após o commit, evitando
que o encerramento posterior do comando reverta visibilidades ou remova o grupo.

### Componente ativo

A geometria é criada no componente atualmente ativado no Fusion. Quando o
componente raiz está ativo, a hélice é criada nele. Quando um componente filho
está ativo, todos os esboços, features, corpos, hub, anéis e spinners são
criados na definição desse componente. A mensagem final informa o nome do
componente de destino.

### Caminhos de seção em componentes aninhados

Os caminhos das seções 3D são criados pelo método `Features.createPath` do
componente ativo. Isso preserva o contexto de componente/montagem das curvas
pertencentes a componentes filhos aninhados.

Quando uma rodada com falha confirma apenas um item na linha do tempo, o add-in
não tenta criar um grupo padrão, pois o Fusion exige pelo menos dois itens. A
mensagem final informa essa condição sem gerar um segundo traceback.

## Versão 1.0

A versão 1.0 é a primeira versão pública estável. Ela promove a base v0.21
completamente testada sem alterar a matemática da hélice nem a geometria
pretendida.

A versão inclui geração no componente ativo, grupos da linha do tempo após a
transação, persistência automática dos parâmetros, restauração dos padrões
originais, interface multilíngue, alternativas de anel de ponta e alternativas
de spinner.

Consulte [docs/RELEASE_NOTES_v1.0.0.md](docs/RELEASE_NOTES_v1.0.0.md) para as
notas da versão e [docs/ROADMAP.md](docs/ROADMAP.md) para o desenvolvimento
planejado.

## Configurações

A versão 1.1 detecta configurações tanto na pasta `configurations/` distribuída
com o add-in quanto em uma pasta persistente `configurations/` do usuário. O
grupo **Configurações** começa expandido. Arquivos JSON existentes na antiga
pasta de usuário `samples/` são copiados para a nova pasta na primeira
descoberta, sem sobrescrever arquivos mais novos.

A interface pode salvar a configuração atual completa como uma nova
configuração do usuário. A lista é atualizada imediatamente, sem reabrir o
comando. Carregar uma configuração apenas preenche a janela: não gera geometria
nem substitui a última configuração executada até que **Gerar** seja
pressionado. A antiga restauração dos padrões está disponível como a
configuração incorporada **Hélice 3 × 1,25 pol. — configuração original**.

São aceitos arquivos com metadados e arquivos normais de configuração plana.
Consulte `configurations/README.md` para os formatos e locais de armazenamento.

### Construção validada com bordo de fuga separado

As cinco configurações de projeto validadas no Fusion usam os padrões da versão 1.1:

```text
Loft construction: Open main surface + separate trailing edge
Loft section order: Root to tip
Loft guides: None
Boundary overlap — diameter: 0,1 mm
```

A superfície NACA aberta é loftada sem o fechamento do bordo de fuga. Um
segundo loft estreito fecha o bordo e sempre usa duas rails nos vértices exatos.
Quando o corte da base é solicitado, as duas superfícies são aparadas pelo plano
XY antes do Stitch. O Boundary Fill usa então a casca costurada, os cilindros
interno e externo e o plano XY.

Perfil fechado, rails distribuídas na superfície principal, ordem inversa,
finalização legada e Automático robusto continuam disponíveis como opções
avançadas ou de compatibilidade.

### Atualização da versão em Scripts and Add-Ins

O Fusion lê a versão mostrada antes de executar o add-in diretamente do
arquivo `.manifest`. Pare o add-in, substitua a pasta inteira — incluindo o
manifesto — e reinicie o Fusion. Substituir apenas o arquivo Python pode manter
a versão antiga na janela Scripts and Add-Ins.

### Finalização sólida por Boundary Fill

Boundary Fill agora é o método padrão para formar a pá sólida. A seção da raiz
é posicionada radialmente para dentro e a seção da ponta para fora pela metade
da sobreposição de diâmetro configurada (padrão `0,1 mm`). Corda, passo,
sweep e interpolação dos perfis continuam usando os raios nominais. O loft e os
cilindros interno e externo nominais definem as células disponíveis. O add-in
seleciona a célula de volume positivo com maior volume e verifica que a operação
produziu exatamente um corpo sólido.

No modo manual **Superfície principal aberta + bordo de fuga separado**, a
superfície NACA aberta usa a configuração de guides escolhida na interface,
enquanto o fechamento do bordo de fuga recebe sempre duas rails nos vértices
exatos. Quando
`Cut_Below_Hub_Base` está marcado, as duas superfícies são aparadas juntas pelo
plano XY antes da costura. A costura preserva a abertura inferior e o Boundary
Fill usa a casca costurada, os cilindros interno/externo e o próprio plano XY
para fechar a célula. O plano XY também é incluído quando não existe material
abaixo de `Z=0`; nesse caso ele simplesmente não cria uma divisão adicional.

O modo de perfil fechado e o fluxo anterior de extensão, trims e costura foram
mantidos como opções legadas em Construção avançada.

### Rails distribuídas e avaliação do acabamento

As rails distribuídas aceitam quantidades ímpares `3, 5, 7, 9...`; o padrão
temporário é 9. Três posições são obrigatórias: duas âncoras simétricas na
região do bordo de fuga e uma no bordo de ataque. Os pares adicionais são
distribuídos igualmente no extradorso e intradorso. A checkbox temporária
alterna as duas primeiras rails entre os vértices exatos do bordo de fuga e os
primeiros pontos internos do perfil.

A avaliação de qualidade compara o loft com a seção teórica que o gerador sabe
calcular em qualquer raio. Para cada intervalo radial interno, são amostrados
pontos do perfil no raio médio. Os três intervalos com maior erro também são
avaliados em 25% e 75% do vão. A decisão usa o **maior erro local normalizado
pela corda**, não apenas a média RMS; assim, uma ondulação limitada a metade da
pá ainda reprova o candidato.

As opções persistentes são:

```json
{
  "Loft_Quality_Check": true,
  "Loft_Quality_Max_Deviation_Percent": 0.1
}
```

`0.1` significa 0,1% da corda local e é um limite temporário para calibração
com os testes visuais. O relatório final informa erro máximo, RMS, raio e índice
de contorno do pior ponto. O overlap inicial padrão do Boundary Fill é `0,1 mm`; o modo robusto mantém esse valor como limite superior de suas tentativas.

As distribuições por espaçamento e slices não inserem uma seção obrigatória em
`Transition_Point`; o perfil NACA intermediário continua controlando a
interpolação contínua.

### Compatibilidade com Part Design

O tipo Part Design do Fusion admite um único componente. Por isso, o preflight
robusto usa duas estratégias de isolamento:

- **Hybrid Design:** cada candidato é criado em um componente-filho oculto e
  descartável;
- **Part ou Assembly Design:** cada candidato é criado no componente ativo e
  removido comparando seus tokens com um snapshot feito imediatamente antes da
  tentativa.

A limpeza segue a ordem de dependência: Boundary Fill, extrusões dos cilindros,
loft, esboços das rails/seções e eventuais corpos órfãos. Uma divergência na
limpeza interrompe a busca, em vez de deixar geometria de diagnóstico no modelo.

### Rails uniformes na corda e qualidade angular

O posicionamento recomendado é **Uniforme na corda**. Uma rail passa pelo bordo
de ataque e as demais são distribuídas em pares, nas mesmas posições x/c, no
extradorso e intradorso.

O Automático robusto usa a quantidade como limite superior, mas procura pelo
menos em `0 -> 3 -> 5 -> 7 -> 9` quando a resolução permite. A aprovação exige
desvio posicional e ângulo estimado de ondulação. O limite angular de fábrica é
`0,2°`.

### Busca robusta cancelável e logs de diagnóstico

O Automático robusto exibe uma janela nativa de progresso do Fusion com o botão
**Cancelar busca**. O cancelamento é cooperativo: ele é verificado durante a
criação das seções e amostras de qualidade e entre operações do kernel. Uma
chamada longa já em execução precisa retornar antes que o cancelamento seja
atendido.

Cada busca robusta grava dois arquivos na pasta de configuração do usuário:

```text
robust_search_logs/robust_search_<data UTC>_<sessão>.json
robust_search_logs/robust_search_<data UTC>_<sessão>.txt
```

O JSON serve para comparação automática. O TXT apresenta os mesmos dados de
forma legível. Ambos preservam todos os candidatos iniciados, inclusive a
tentativa parcial cancelada, tempos por etapa, qualidade, volumes do Boundary
Fill, erros e resultado da limpeza.

### Comportamento da janela de progresso

O total da janela conta somente estratégias distintas de loft:

```text
ordem das seções × quantidade de rails × estado de merge
```

As repetições de overlap do Boundary Fill continuam registradas como tentativas
separadas, mas não aumentam artificialmente o total mostrado. Fechar a janela
de progresso é interpretado como cancelamento depois que ela aparece. A janela
mostra apenas textos compactos; as mensagens completas do kernel permanecem nos
logs salvos.
