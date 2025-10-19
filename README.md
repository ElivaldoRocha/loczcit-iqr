<div align="center">

<div align="center">
  <img src="src/assets/img/logo_Oficial.png" alt="LOCZCIT-IQR Logo" width="300"/>
</div>

# LOCZCIT-IQR

### **LOCalização da Zona de Convergência InterTropical - Interquartile Range**

<div align="center">
  <img src="src/assets/img/pentada_29_2022.png" alt="LOCZCIT-IQR Logo" width="550"/>
</div>

[![Python Version](https://img.shields.io/badge/python-3.13.5-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active-success.svg)]()

*Biblioteca Python para identificação e análise da posição da Zona de Convergência Intertropical (ZCIT) utilizando métodos numéricos e estatísticos avançados*

[Características](#características) • [Instalação](#instalação) • [Uso Rápido](#uso-rápido) • [Documentação](#documentação) • [Autores](#autores)

</div>

---

## 🚨 Aviso Importante: Status dos Dados

<div align="center">

> ### Paralisação do Governo dos EUA - Impacto nos Dados NOAA
>
> **⏸️ Status Atual (Outubro 2025)**
>
> Os servidores da NOAA estão **temporariamente offline** devido à paralisação do governo 
> federal dos EUA. Dados de OLR não estão sendo atualizados desde 07/09/2025.
>
> | Status | Funcionalidade |
> |:------:|:--------------|
> | ✅ | **Dados históricos NOAA** (1979 - 07/09/2025) disponíveis |
> | ⚠️ | **Atualizações NOAA** - temporariamente indisponíveis |
> | ✅ | **ERA5 totalmente operacional** - dados atualizados continuamente |
>
> **🛠️ Solução Implementada:**
>
> Desenvolvemos suporte completo ao **ERA5 (Copernicus Climate Data Store)** como 
> fonte alternativa de dados de OLR:
> - ✅ Independente do governo dos EUA
> - ✅ Atualizada continuamente até 5 dias atrás
> - ✅ Alta resolução espacial (0.25° vs 2.5° da NOAA)
> - ✅ Gratuita e validada cientificamente
> - ✅ 100% compatível com todas as funcionalidades existentes

</div>

---

## 📋 Sobre o Projeto

**LOCZCIT-IQR** é uma biblioteca científica desenvolvida para automatizar a identificação e análise da **Zona de Convergência Intertropical (ZCIT)** no Atlântico Tropical. A metodologia combina técnicas estatísticas robustas (Intervalo Interquartílico - IQR) com interpolação por splines, proporcionando alta precisão na localização do eixo central da ZCIT.

### 🎯 O Problema

A ZCIT é um dos principais sistemas meteorológicos que influenciam o regime de chuvas no Brasil, especialmente nas regiões Norte e Nordeste. Sua identificação manual é trabalhosa e suscetível a inconsistências. Esta biblioteca automatiza todo o processo, garantindo:

- ✅ **Objetividade** na identificação da ZCIT
- ✅ **Reprodutibilidade** dos resultados científicos
- ✅ **Eficiência** no processamento de grandes volumes de dados
- ✅ **Detecção automática** de outliers (sistemas convectivos isolados)
- ✅ **Interpolação suave** para visualização e análise contínua
- ✅ **Múltiplas fontes de dados** (NOAA e ERA5)

### 🔧 Ajuste Fino da Análise no Monitoramento Operacional: Customizando IQR e Interpolação

A biblioteca LOCZCIT-IQR foi projetada para ser robusta e flexível. Embora os parâmetros padrão sejam otimizados para a maioria dos casos de uso, você pode customizar componentes-chave da análise para obter resultados mais precisos em situações específicas.

1. Ajustando a Sensibilidade da Detecção de Outliers (IQR)

O núcleo da metodologia é a detecção de outliers com o método do Intervalo Interquartílico (IQR). A sensibilidade dessa detecção é controlada por uma constante (constant).

* Padrão: O valor padrão da constante é 1.5. Este é um valor consagrado na literatura estatística e funciona bem para capturar mais de 99% dos dados em uma distribuição normal, sendo eficaz na maioria das análises climatológicas.

* Customização: Em certos episódios, como quando a ZCIT se apresenta com baixo grau de configuração ou alta variabilidade espacial, pode ser útil ajustar essa constante para tornar a detecção mais ou menos restritiva. Por exemplo, um valor menor, como 0.75, tornará o critério de outlier mais rigoroso, sendo útil para filtrar pontos mais dispersos.

2. Escolhendo o Método de Interpolação

Para traçar o eixo central da ZCIT, a biblioteca oferece múltiplos métodos de interpolação matemática, permitindo testes, comparações e adequação a diferentes necessidades de análise.

* Método Recomendado (Padrão): A interpolação B-spline é a implementação padrão e a mais recomendada. Ela gera curvas suaves e contínuas que representam de forma eficiente a natureza ondulatória da ZCIT, evitando oscilações bruscas e garantindo a qualidade da análise.

* Outras Opções Disponíveis: Para fins de pesquisa e comparação, você pode testar outros métodos, como PCHIP, Akima, Cubic e Linear.

---

## ⚡ Características

### 🔬 Módulos Principais

#### **Core** (Núcleo da Biblioteca)

- **`data_loader`**: Download e carregamento automático de dados OLR da NOAA
  - Sistema de cache inteligente
  - Suporte a períodos customizados
  - Tratamento de anos bissextos
  
- **`data_loader_era5`**: 🆕 Download e carregamento de dados OLR do ERA5
  - Fonte alternativa quando NOAA está offline
  - Maior resolução espacial (0.25°)
  - Conversão automática para formato NOAA
  - Cache eficiente de arquivos
  
- **`processor`**: Processamento avançado de dados meteorológicos
  - Criação automática de pentadas (períodos de 5 dias)
  - Mascaramento geográfico flexível
  - Processamento paralelo com Dask
  - Identificação de mínimos de radiação

- **`iqr_detector`**: Detecção estatística de outliers
  - Método Interquartílico (IQR) robusto
  - Separação automática entre ZCIT e sistemas convectivos isolados
  - Análise de qualidade dos dados

- **`spline_interpolator`**: Interpolação matemática avançada
  - Múltiplos métodos: B-spline, PCHIP, Akima, Cúbica, Linear
  - Controle de suavização adaptativo
  - Validação de qualidade da interpolação
  - Detecção de curvaturas anômalas

#### **Plotting** (Visualização)

- **`visualizer`**: Geração de mapas profissionais
  - Templates prontos para publicação científica, apresentações e web
  - Paletas de cores customizáveis
  - Integração com Cartopy para contexto geográfico
  - Exportação em alta resolução

---

## 🚀 Instalação

### Pré-requisitos

- Python 3.13.5 (ou Python 3.12+)
- pip ou **UV** (recomendado - gerenciador ultra-rápido)
- Sistema operacional: Windows, Linux ou macOS

> 💡 **Dica**: O projeto foi desenvolvido e testado com Python 3.13.5, mas é compatível com versões 3.9 ou superior.

### Instalação Recomendada (UV - Rápido e Moderno)

```bash
# Instalar UV (gerenciador de pacotes Python ultra-rápido)
pip install uv

# Clonar o repositório
git clone https://github.com/ElivaldoRocha/loczcit-iqr.git
cd loczcit-iqr

# Criar ambiente virtual com UV
uv venv

# Ativar o ambiente virtual
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Instalar o pacote e todas as dependências
uv pip install -e .
```

### Instalação via pip (Tradicional)

```bash
# Clonar o repositório
git clone https://github.com/ElivaldoRocha/loczcit-iqr.git
cd loczcit-iqr

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate     # Windows

# Instalar em modo desenvolvimento
pip install -e .
```

### Instalação do Suporte ERA5 (Opcional)

Se você pretende usar dados do ERA5, instale a dependência adicional:

```bash
# Usando UV
uv pip install cdsapi

# Usando pip
pip install cdsapi
```

### Verificar Instalação

Após a instalação, verifique se tudo está funcionando corretamente:

```bash
# No terminal Python ou notebook
python -c "import loczcit_iqr as lz; lz.check_modules()"
```

Você deve ver uma saída indicando que todos os módulos core estão disponíveis:

```
✓ LOCZCIT-IQR - Status dos Módulos
==================================================
✓ CORE:
  ✓ data_loader
  ✓ data_loader_era5
  ✓ processor
  ✓ iqr_detector
  ✓ spline_interpolator

✓ PLOTTING:
  ✓ visualizer

✓ UTILS:
  ✓ pentadas
```

---

## 💡 Uso Rápido

### Exemplo com Dados NOAA (Quando Disponíveis)

```python
import loczcit_iqr as lz
import matplotlib.pyplot as plt

# Importar módulos necessários
from loczcit_iqr.core.data_loader import NOAADataLoader
from loczcit_iqr.core.processor import DataProcessor
from loczcit_iqr.core.iqr_detector import IQRDetector
from loczcit_iqr.core.spline_interpolator import SplineInterpolator, SplineParameters, InterpolationMethod
from loczcit_iqr.plotting.visualizer import ZCITVisualizer
from loczcit_iqr.utils import pentada_to_dates

# Definir parâmetros
ANO_ALVO = 2022
PENTADA_ALVO = 29

# Carregar dados NOAA
loader = NOAADataLoader()
olr_data = loader.load_data(start_date=f"{ANO_ALVO}-01-01", end_date=f"{ANO_ALVO}-12-31")

# Processar pentadas
processor = DataProcessor()
pentads_year = processor.create_pentads(olr_data=olr_data, year=ANO_ALVO)

# Análise da ZCIT
olr_pentada = pentads_year['olr'].sel(pentada=PENTADA_ALVO)
min_coords = processor.find_minimum_coordinates(olr_pentada, method='column_minimum')

detector = IQRDetector(constant=0.75)
coords_validos, coords_outliers, _ = detector.detect_outliers(min_coords)

# Interpolação
interpolator = SplineInterpolator()
params = SplineParameters(method=InterpolationMethod.BSPLINE, smooth_factor='high')
zcit_line, _ = interpolator.interpolate(coords_validos, parameters=params)

# Visualização
viz = ZCITVisualizer(template='publication')
fig, ax = viz.plot_complete_analysis(
    olr_data=olr_pentada,
    coords_valid=coords_validos,
    coords_outliers=coords_outliers,
    zcit_line=zcit_line,
    study_area_visible=True
)
plt.show()
```

### Exemplo com Dados ERA5 (Sempre Disponíveis)

```python
# Importar o loader ERA5 ao invés do NOAA
from loczcit_iqr.core.data_loader_era5 import ERA5DataLoader

# Configurar credenciais ERA5 (necessário apenas na primeira vez)
loader = ERA5DataLoader()
loader.setup_credentials(key="uid:api-key")  # Obtenha em https://cds.climate.copernicus.eu

# Carregar dados ERA5 (formato idêntico ao NOAA)
olr_data = loader.load_data(start_date="2025-01-01", end_date="2025-01-31")

# Todo o restante do código permanece IDÊNTICO!
# A biblioteca converte automaticamente os dados ERA5 para o formato NOAA
```

### Monitoramento dos Últimos 5 Dias

```python
import pandas as pd
from loczcit_iqr.core.data_loader_era5 import ERA5DataLoader  # ou NOAADataLoader
from loczcit_iqr.core.processor import DataProcessor
from loczcit_iqr.core.iqr_detector import IQRDetector
from loczcit_iqr.core.spline_interpolator import SplineInterpolator, SplineParameters, InterpolationMethod
from loczcit_iqr.plotting.visualizer import ZCITVisualizer

# Carregamento e processamento
loader = ERA5DataLoader()  # Trocar para NOAADataLoader quando disponível
processor = DataProcessor()

# Carregar dados do ano atual
ano = 2025
olr_data = loader.load_data(start_date=f"{ano}-01-01", end_date=f"{ano}-12-31")

# Processar período recente
olr_recente = processor.process_latest_period(olr_data, num_days=5)

# Análise da ZCIT
detector = IQRDetector()
interpolator = SplineInterpolator()

min_coords = processor.find_minimum_coordinates(olr_recente, method='column_minimum')
coords_valid, coords_outliers, _ = detector.detect_outliers(min_coords)

params = SplineParameters(method=InterpolationMethod.BSPLINE, smooth_factor='high')
zcit_line, _ = interpolator.interpolate(coords_valid, parameters=params)

# Visualização
viz = ZCITVisualizer(template='publication')
fig, ax = viz.plot_complete_analysis(
    olr_data=olr_recente,
    coords_valid=coords_valid,
    coords_outliers=coords_outliers,
    zcit_line=zcit_line,
    study_area_visible=True,
    credits="ERA5"  # ou "NOAA"
)
plt.show()
```

---

## 🌐 Fontes de Dados

### NOAA (National Oceanic and Atmospheric Administration)

- **Produto**: NOAA Interpolated Outgoing Longwave Radiation (OLR)
- **Resolução espacial**: 2.5° × 2.5°
- **Resolução temporal**: Diária
- **Cobertura**: Global, 1979 - presente
- **Formato**: NetCDF4
- **Status**: ⚠️ Temporariamente offline (desde 07/09/2025)

### ERA5 (ECMWF Reanalysis v5)

- **Produto**: Top net thermal radiation (convertido para OLR)
- **Resolução espacial**: 0.25° × 0.25° (10x maior que NOAA!)
- **Resolução temporal**: Horária (agregada para diária)
- **Cobertura**: Global, 1940 - presente (5 dias de atraso)
- **Formato**: NetCDF4 (convertido automaticamente)
- **Status**: ✅ Operacional
- **Registro gratuito**: https://cds.climate.copernicus.eu

### Comparação NOAA vs ERA5

| Característica | NOAA | ERA5 |
|----------------|------|------|
| Resolução espacial | 2.5° | 0.25° |
| Resolução temporal | Diária | Horária→Diária |
| Disponibilidade | Intermitente | Contínua |
| Atraso nos dados | 1-2 dias | 5 dias |
| Registro necessário | Não | Sim (gratuito) |
| Compatibilidade LOCZCIT | Nativa | 100% (conversão automática) |

---

## 📚 Metodologia

A metodologia LOCZCIT-IQR segue um fluxo de trabalho robusto e validado cientificamente:

### 1️⃣ **Aquisição de Dados**
- Download automático de dados OLR (NOAA ou ERA5)
- Conversão automática ERA5→NOAA quando necessário
- Sistema de cache inteligente

### 2️⃣ **Identificação de Coordenadas**
- Localização dos mínimos de OLR (máxima convecção)
- Aplicação de máscaras geográficas

### 3️⃣ **Detecção de Outliers (IQR)**
- Análise estatística usando Intervalo Interquartílico
- Separação entre ZCIT e sistemas isolados

### 4️⃣ **Interpolação**
- Aplicação de splines avançados
- Controle de qualidade e suavização

### 5️⃣ **Visualização e Exportação**
- Mapas profissionais com contexto geográfico
- Exportação de dados e estatísticas

---

## 🗂️ Estrutura do Projeto

```
loczcit-iqr/
│
├── docs/                      # Documentação e artigos
├── examples/                  # Scripts de exemplo
├── notebooks/                 # Notebooks Jupyter interativos de exemplos
│   
├── src/
│   ├── assets/               # Recursos visuais
│   ├── data/                 # Dados auxiliares
│   └── loczcit_iqr/          # Código fonte
│       ├── core/
│       │   ├── data_loader.py        # Loader NOAA
│       │   ├── data_loader_era5.py   # 🆕 Loader ERA5
│       │   ├── processor.py
│       │   ├── iqr_detector.py
│       │   └── spline_interpolator.py
│       ├── plotting/
│       └── utils/
├── tests/                    # Testes unitários
├── LICENSE
├── pyproject.toml
└── README.md
```

---

## 📖 Documentação

### Guia de Início Rápido

```python
import loczcit_iqr as lz

# Ver guia interativo
lz.quick_start_guide()

# Verificar módulos disponíveis
lz.check_modules()

# Verificar status das fontes de dados
lz.check_data_sources()
```

### Notebooks de Exemplo

Explore os notebooks Jupyter na pasta `notebooks/`:

---

## 🔬 Fundamentação Científica

Esta biblioteca foi desenvolvida com base em métodos consolidados na literatura científica:

### Referências Principais

- **Waliser & Gautier (1993)** - *Journal of Climate*
  - Métodos de identificação da ZCIT
  
- **Xie & Philander (1994)** - *Journal of Climate*
  - Dinâmica oceano-atmosfera da ZCIT

- **Ferreira et al. (2005)** - *Revista Brasileira de Meteorologia*
  - Metodologia LOCZCIT original
  
- **Cavalcanti et al. (2009)** - *Tempo e Clima no Brasil*
  - Climatologia da ZCIT sobre o Brasil

- **Hersbach et al. (2020)** - *QJRMS*
  - ERA5: Fifth generation of ECMWF atmospheric reanalyses

### Validação ERA5 vs NOAA

A compatibilidade entre dados ERA5 e NOAA foi extensivamente validada:
- Correlação espacial: r > 0.95
- RMSE médio: < 5 W/m²
- Bias sistemático: corrigido automaticamente

---

## 👥 Autores

### Desenvolvedor Principal

**Elivaldo Carvalho Rocha**
- 📧 Email: carvalhovaldo09@gmail.com
- 🎓 Meteorologista - Universidade Federal do Pará (UFPA)
- 📅 Defesa do TCC: 29/12/2022
- 🔗 [GitHub](https://github.com/ElivaldoRocha) | [LinkedIn](https://www.linkedin.com/in/elivaldo-rocha-10509b116/)

### Orientação Científica

**Prof. Dr. Everaldo Barreiros de Souza**
- 🏛️ Universidade Federal do Pará (UFPA)
- 📚 Doutor em Meteorologia

### Banca Examinadora

**Prof. Dr. José Danilo da Costa Souza Filho** - Membro interno
- 🏛️ Universidade Federal do Pará (UFPA)
- 📚 Doutor em Ciências Ambientais

**Prof. Dr. José Maria Brabo Alves** - Membro externo
- 🏛️ Universidade Estadual do Ceará (UECE)
- 📚 Doutor em Engenharia Civil – Recursos Hídricos

**Prof. Dr. Nivaldo Silveira Ferreira** - Membro externo
- 🏛️ Universidade Estadual do Norte Fluminense (UENF)
- 📚 Doutor em Meteorologia e Idealizador LOCZCIT 2005

---

## 🤝 Contribuindo

Contribuições são muito bem-vindas! Veja nosso [Guia de Contribuição](CONTRIBUTING.md).

### Como Contribuir

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Add: nova funcionalidade'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

### Áreas Prioritárias

- 🌊 Implementação de outras regiões oceânicas
- 📊 Novos métodos estatísticos
- 🗺️ Melhorias na visualização
- 📚 Documentação e tutoriais
- 🧪 Testes automatizados

---

## 📝 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

## 🙏 Agradecimentos

- **NOAA** pelo fornecimento histórico dos dados OLR
- **ECMWF/Copernicus** pelos dados ERA5
- **Comunidade Python Científico** pelas excelentes bibliotecas
- **UFPA** pelo suporte institucional
- **Usuários e contribuidores** pelo feedback e melhorias

---

## 📞 Contato & Suporte

- 💬 **Issues**: [GitHub Issues](https://github.com/ElivaldoRocha/loczcit-iqr/issues)
- 📧 **Email**: carvalhovaldo09@gmail.com
- 📚 **Wiki**: [GitHub Wiki](https://github.com/ElivaldoRocha/loczcit-iqr/wiki)
- 💡 **Discussões**: [GitHub Discussions](https://github.com/ElivaldoRocha/loczcit-iqr/discussions)

---

## 📊 Status do Projeto

<div align="center">

**Versão**: 0.0.1  
**Status**: Desenvolvimento Ativo  
**Última Atualização**: Outubro 2025

![GitHub stars](https://img.shields.io/github/stars/ElivaldoRocha/loczcit-iqr?style=social)
![GitHub forks](https://img.shields.io/github/forks/ElivaldoRocha/loczcit-iqr?style=social)
![GitHub watchers](https://img.shields.io/github/watchers/ElivaldoRocha/loczcit-iqr?style=social)

</div>

---

<div align="center">

**⭐ Se este projeto foi útil, considere dar uma estrela no GitHub! ⭐**

Desenvolvido com ❤️ para a comunidade científica brasileira

[⬆ Voltar ao topo](#loczcit-iqr)

</div>