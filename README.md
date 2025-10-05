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

## 📋 Sobre o Projeto

**LOCZCIT-IQR** é uma biblioteca científica desenvolvida para automatizar a identificação e análise da **Zona de Convergência Intertropical (ZCIT)** no Atlântico Tropical. A metodologia combina técnicas estatísticas robustas (Intervalo Interquartílico - IQR) com interpolação por splines, proporcionando alta precisão na localização do eixo central da ZCIT.

### 🎯 O Problema

A ZCIT é um dos principais sistemas meteorológicos que influenciam o regime de chuvas no Brasil, especialmente nas regiões Norte e Nordeste. Sua identificação manual é trabalhosa e suscetível a inconsistências. Esta biblioteca automatiza todo o processo, garantindo:

- ✅ **Objetividade** na identificação da ZCIT
- ✅ **Reprodutibilidade** dos resultados científicos
- ✅ **Eficiência** no processamento de grandes volumes de dados
- ✅ **Detecção automática** de outliers (sistemas convectivos isolados)
- ✅ **Interpolação suave** para visualização e análise contínua

---

## ⚡ Características

### 🔬 Módulos Principais

#### **Core** (Núcleo da Biblioteca)

- **`data_loader`**: Download e carregamento automático de dados OLR da NOAA
  - Sistema de cache inteligente
  - Suporte a períodos customizados
  - Tratamento de anos bissextos
  
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

- Python 3.13.5 (ou Python 3.9+)
- pip ou **UV** (recomendado - gerenciador ultra-rápido)
- Sistema operacional: Windows, Linux ou macOS

> 💡 **Dica**: O projeto foi desenvolvido e testado com Python 3.13.5, mas é compatível com versões 3.9 ou superior.

### Instalação Recomendada (UV - Rápido e Moderno)

```bash
# Instalar UV (gerenciador de pacotes Python ultra-rápido)
pip install uv

# Clonar o repositório
git clone https://github.com/seu-usuario/loczcit-iqr.git
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
git clone https://github.com/seu-usuario/loczcit-iqr.git
cd loczcit-iqr

# Criar ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate     # Windows

# Instalar em modo desenvolvimento
pip install -e .
```

### Instalação Rápida de Dependências

Se você já tem um ambiente virtual ativo, pode instalar apenas as dependências principais:

```bash
# Usando UV (recomendado - muito mais rápido!)
uv pip install numpy xarray scipy matplotlib cartopy pandas \
               geopandas dask regionmask netcdf4 shapely

# Usando pip tradicional
pip install numpy xarray scipy matplotlib cartopy pandas \
            geopandas dask regionmask netcdf4 shapely
```

**Nota**: O comando `uv pip install -e .` já instala todas as dependências automaticamente baseado no arquivo `pyproject.toml`.

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
  ✓ processor
  ✓ iqr_detector
  ✓ spline_interpolator

✓ PLOTTING:
  ✓ visualizer

✓ UTILS:
  ✓ pentadas
```

### Dependências Principais

**Core (Obrigatórias):**
- `numpy` == 2.3.3 (Computação numérica)
- `xarray` == 2025.9.0 (Manipulação de arrays multidimensionais)
- `scipy` == 1.16.2 (Algoritmos científicos e interpolação)
- `matplotlib` == 3.10.6 (Visualização de dados)
- `cartopy` == 0.25.0 (Mapas e projeções cartográficas)
- `pandas` == 2.3.2 (Análise de dados tabulares)
- `shapely` == 2.1.2 (Operações geométricas)
- `netcdf4` == 1.7.2 (Leitura de arquivos NetCDF)
- `pyarrow` == 21.0.0 (Leitura de arquivos Parquet)

**Processamento e Análise:**
- `geopandas` == 1.1.1 (Dados geoespaciais)
- `regionmask` == 0.13.0 (Máscaras geográficas otimizadas)
- `dask` == 2025.9.1 (Processamento paralelo)
- `h5netcdf` == 1.6.4 (Backend alternativo para NetCDF)
- `cftime` == 1.6.4.post1 (Manipulação de calendários)

**Visualização Avançada:**
- `seaborn` == 0.13.2 (Visualizações estatísticas)
- `matplotlib-scalebar` == 0.9.0 (Barras de escala em mapas)
- `imageio` == 2.37.0 (Manipulação de imagens)
- `pillow` == 11.3.0 (Processamento de imagens)

**Georreferenciamento:**
- `rasterio` == 1.4.3 (Dados raster)
- `pyproj` == 3.7.2 (Transformações de coordenadas)
- `pyogrio` == 0.11.1 (I/O geoespacial rápido)
- `geopy` == 2.4.1 (Geocodificação)

---

## 💡 Uso Rápido

### Exemplo Básico

```python
import loczcit_iqr as lz

# Verificar instalação
lz.check_modules()

# Carregar dados NOAA OLR
from loczcit_iqr.core.data_loader import NOAADataLoader

loader = NOAADataLoader()
olr_data = loader.load_data(
    start_date="2024-01-01",
    end_date="2024-12-31"
)

# Processar dados em pentadas
from loczcit_iqr.core.processor import DataProcessor

processor = DataProcessor(use_dask=True, n_workers=4)
pentads = processor.create_pentads(olr_data, year=2024)

# Encontrar coordenadas da ZCIT
coords = processor.find_minimum_coordinates(pentads['olr'])

# Detectar e remover outliers
from loczcit_iqr.core.iqr_detector import IQRDetector

detector = IQRDetector()
coords_validos, coords_outliers = detector.detect_and_filter(coords)

# Interpolar linha da ZCIT
from loczcit_iqr.core.spline_interpolator import SplineInterpolator

interpolator = SplineInterpolator()
linha_zcit, stats = interpolator.interpolate(
    coords_validos,
    method='bspline',
    smooth_factor='auto'
)

# Visualizar resultado
from loczcit_iqr.plotting.visualizer import plot_zcit_quick

fig = plot_zcit_quick(pentads['olr'], pentada=10, year=2024)
```

### Análise Climatológica

```python
from loczcit_iqr.utils.climatologia import (
    climatologia_nordeste_brasileiro,
    comparar_com_climatologia_cientifica
)

# Calcular climatologia para o Nordeste (1992-2021)
clima = climatologia_nordeste_brasileiro(
    anos_amostra=range(1992, 2022)
)

# Comparar posição observada com climatologia
status, desvio, interpretacao = comparar_com_climatologia_cientifica(
    mes=3,
    posicao_encontrada=-2.5
)

print(f"Status: {status}")
print(f"Desvio: {desvio:.2f}°")
print(f"Interpretação: {interpretacao}")
```

---

## 📚 Metodologia

A metodologia LOCZCIT-IQR segue um fluxo de trabalho robusto e validado cientificamente:

### 1️⃣ **Identificação de Coordenadas**
Localização das coordenadas que marcam a máxima atuação da convecção (mínimos de ROL/OLR)

### 2️⃣ **Armazenamento**
Guardar coordenadas em estrutura de dados otimizada

### 3️⃣ **Detecção de Outliers** (IQR)
Análise estatística para identificar sistemas convectivos isolados usando o método do Intervalo Interquartílico

### 4️⃣ **Interpolação**
Aplicação de splines (B-spline, PCHIP, etc.) com controle de suavização para gerar linha contínua da ZCIT

### 5️⃣ **Exportação**
Geração do eixo central da ZCIT com metadados e estatísticas de qualidade

---

## 🗂️ Estrutura do Projeto

```
loczcit-iqr/
│
├── src/
│   ├── loczcit_iqr/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── data_loader.py       # Download e carregamento de dados
│   │   │   ├── processor.py         # Processamento de pentadas
│   │   │   ├── iqr_detector.py      # Detecção de outliers
│   │   │   └── spline_interpolator.py  # Interpolação matemática
│   │   │
│   │   ├── plotting/
│   │   │   └── visualizer.py        # Visualização e mapas
│   │   │
│   │   └── utils/
│   │       ├── pentadas.py      # Conversão e manipulação de pentadas
│   │       └── validators.py    # Funções de validação 
│   │
│   ├── data/
│   │   └── shapefiles/              # Arquivos de área de estudo
│   │
│   └── assets/
│       └── img/
│           └── logo_Oficial.png     # Logo do projeto
│
├── notebooks/                        # Exemplos de uso
├── docs/                             # TCC e Documentação completa
├── README.md
├── LICENSE
└── setup.py
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
```

### Documentação Completa

Acesse a documentação completa em: [https://loczcit-iqr.readthedocs.io](https://loczcit-iqr.readthedocs.io) *(em breve)*

### Notebooks de Exemplo

Explore os notebooks Jupyter na pasta `examples/`:
- `data_loader.ipynb` - Carregamento de dados NOAA
- `processor_and_Interpolator.ipynb` - Processamento de pentadas, Detecção de outliers e Interpolação avançada
- `work_flow.ipynb` - Exemplo sugerido de fluxo de trabalho

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

- **NOAA Climate Data Record (1979-2023)**
  - Dados de Radiação de Onda Longa (OLR)

### Dados Utilizados

- **Fonte**: NOAA Interpolated Outgoing Longwave Radiation (OLR)
- **Resolução espacial**: 2.5° × 2.5° (latitude × longitude)
- **Resolução temporal**: Diária
- **Cobertura**: Global, 1979 - presente
- **Formato**: NetCDF4

---

## 👥 Autores

### Desenvolvedor e Autor

**Elivaldo Carvalho Rocha**
- 📧 Email: carvalhovaldo09@gmail.com
- 🎓 Meteorologista - Universidade Federal do Pará (UFPA)
- 📅 Data da defesa: 29/12/2022
- 🔗 [GitHub](https://github.com/ElivaldoRocha) | [LinkedIn](https://www.linkedin.com/in/elivaldo-rocha-10509b116/)

### Orientação Científica

**Prof. Dr. Everaldo Barreiros de Souza** - Orientador
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
- 📚 Doutor em Meteorologia

---

## 🤝 Contribuindo

Contribuições são muito bem-vindas! Se você deseja melhorar esta biblioteca:

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/MinhaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona MinhaFeature'`)
4. Push para a branch (`git push origin feature/MinhaFeature`)
5. Abra um Pull Request

### Diretrizes

- Siga as convenções PEP 8 para código Python
- Adicione testes para novas funcionalidades
- Atualize a documentação conforme necessário
- Mantenha o código limpo e bem comentado

---

## 📝 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

## 🙏 Agradecimentos

- **NOAA** pelo fornecimento dos dados de OLR
- **Comunidade Python Científico** pelas excelentes bibliotecas
- **UFPA** pelo suporte institucional
- **Projeto Original LOCZCIT** por Ferreira et al. (2005)

---

## 📞 Contato & Suporte

- 💬 **Issues**: [GitHub Issues](https://github.com/seu-usuario/loczcit-iqr/issues)
- 📧 **Email**: carvalhovaldo09@gmail.com
- 📖 **Documentação**: [ReadTheDocs](https://loczcit-iqr.readthedocs.io)

---

## 📊 Status do Projeto

**Versão Atual**: 0.0.1  
**Status**: Desenvolvimento Ativo  
**Última Atualização**: Outubro 2025

---

<div align="center">

**⭐ Se este projeto foi útil para você, considere dar uma estrela no GitHub! ⭐**

Feito com ❤️ para a comunidade científica brasileira

[⬆ Voltar ao topo](#loczcit-iqr)

</div>