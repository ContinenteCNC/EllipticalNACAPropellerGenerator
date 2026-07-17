# Gerador de Hélices NACA Elípticas

[English](README.md) | [Português do Brasil](README.pt-BR.md)


Add-in multilíngue para Autodesk Fusion que gera hélices paramétricas
completas, com planta elíptica e transições suaves entre aerofólios NACA de
quatro dígitos.

Versão atual: **v1.0.0**

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
- Salvamento atômico dos parâmetros atuais no JSON.
- Janela compacta organizada em grupos recolhíveis.

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

A última configuração do usuário é armazenada fora do repositório e da pasta
de instalação do add-in:

```text
Windows: %APPDATA%\EllipticalNACAPropellerGenerator\propeller_user_config.json
macOS:   ~/Library/Application Support/EllipticalNACAPropellerGenerator/propeller_user_config.json
```

Use **Restaurar padrões originais** para recarregar os valores distribuídos e
remover a configuração salva. A restauração não gera geometria.

### Organização da linha do tempo

Em projetos paramétricos, cada rodada é agrupada somente depois que o Fusion
dispara o evento global `commandTerminated`, quando a transação do comando já
terminou e os novos itens estão disponíveis na linha do tempo. Os grupos são
criados recolhidos e recebem nomes sequenciais:

```text
Elliptical NACA Propeller 01
Elliptical NACA Propeller 02
...
```

A mensagem final da geração também é adiada até essa etapa posterior à
transação, portanto sempre informa se o agrupamento funcionou, falhou ou foi
ignorado de forma intencional. O nome visível do comando inclui a versão atual.

Os objetos da API da timeline são verificados explicitamente com `is None` e `isValid`, portanto uma timeline válida e vazia na primeira rodada é aceita.

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
