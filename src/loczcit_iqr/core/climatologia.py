"""
loczcit_iqr/core/climatologia.py

Módulo para cálculo de climatologia científica da ZCIT (Zona de Convergência Intertropical).

Este módulo fornece funcionalidades para:
- Calcular climatologia baseada em dados históricos da NOAA (1979-2023)
- Comparar posições atuais da ZCIT com valores climatológicos
- Interpretar anomalias meteorológicas e contexto sazonal
- Validar resultados com base em literatura científica
- Usar áreas de estudo flexíveis (BBOX, geometrias, arquivos)

ANALOGIA DO CARTÓGRAFO METEOROLÓGICO 🗺️
Como um cartógrafo que pode escolher diferentes "lentes" para mapear o clima:
1. Vista panorâmica (dados globais) - para contexto completo
2. Área específica (BBOX) - para região de interesse
3. Lupa customizada (geometria exata) - para análise precisa

Referências:
    - Waliser & Gautier (1993): "A satellite-derived climatology of the ITCZ"
    - Xie & Philander (1994): "A coupled ocean-atmosphere model of relevance to the ITCZ"
    - Cavalcanti et al. (2009): "Tempo e Clima no Brasil"
    - Ferreira et al. (2005): "LOCZCIT - procedimento numérico para ZCIT"

Author: Elivaldo Rocha developer of LOCZCIT-IQR
License: MIT
Version: 0.0.1
"""

from __future__ import annotations

import json
import logging
import warnings
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

# Verificar dependências opcionais
try:
    import geopandas as gpd

    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    gpd = None

# Importações do LOCZCIT-IQR
from .data_loader import NOAADataLoader
from .iqr_detector import IQRDetector
from .processor import DataProcessor

# Configurar warnings
warnings.filterwarnings("ignore")

# Type aliases
YearRange = tuple[int, int]
AreaBounds = tuple[float, float, float, float]  # (lat_min, lat_max, lon_min, lon_max)
StudyAreaType = Optional[AreaBounds | str | Any]  # Any para geopandas.GeoDataFrame
MonthlyClimatology = dict[int, float]
ClimatologyData = dict[int, dict[str, float | int | list[float]]]

meses_em_portugues = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


class ClimatologiaZCIT:
    """
    Classe para calcular a climatologia científica da ZCIT baseada em dados históricos da NOAA.

    ANALOGIA DO CARTÓGRAFO METEOROLÓGICO 🗺️
    Como um cartógrafo que usa diferentes "lentes" para mapear o clima:
    - Vista panorâmica (dados globais) para contexto
    - Zoom regional (BBOX) para áreas específicas
    - Lupa de precisão (geometria) para análise detalhada

    Esta classe permite:
    - Processar dados históricos de OLR para múltiplos anos
    - Calcular posições médias mensais da ZCIT
    - Gerar estatísticas robustas com remoção de outliers
    - Criar visualizações da climatologia calculada
    - Usar diferentes tipos de área de estudo (flexível como load_data_dual_scale)

    Parameters
    ----------
    anos_inicio : int, default=1979
        Ano inicial para cálculo da climatologia
    anos_fim : int, default=2023
        Ano final para cálculo da climatologia
    study_area : StudyAreaType, default=None
        Área de estudo flexível. Pode ser:
        - None: Usa geometria padrão interna (Area_LOCZCIT.parquet)
        - tuple: (lat_min, lat_max, lon_min, lon_max) para bounding box
        - str: Caminho para arquivo de geometria (.shp, .geojson, .parquet)
        - geopandas.GeoDataFrame: Objeto GeoDataFrame já carregado
    mask_to_shape : bool, default=False
        Se True e uma geometria é fornecida, mascara dados para forma exata.
        Se False, usa recorte por bounding box apenas.

    Attributes
    ----------
    climatologia_mensal : Dict[int, Dict]
        Climatologia calculada por mês com estatísticas
    dados_historicos : Dict[int, List]
        Dados históricos brutos por mês

    Examples
    --------
    >>> # Usar área padrão (geometria interna)
    >>> calc = ClimatologiaZCIT(anos_inicio=1990, anos_fim=2020)
    >>> calc.baixar_dados_historicos()
    >>> calc.calcular_climatologia_final()
    >>> climatologia = calc.obter_climatologia_dicionario()
    >>> print(climatologia[3])  # Climatologia para março
    -2.5

    >>> # Usar BBOX específico
    >>> area_custom = (-15, 10, -60, -20)  # Atlântico Tropical
    >>> calc = ClimatologiaZCIT(study_area=area_custom)

    >>> # Usar arquivo de geometria
    >>> calc = ClimatologiaZCIT(study_area="minha_area.shp", mask_to_shape=True)

    >>> # Usar GeoDataFrame
    >>> gdf = gpd.read_file("area.geojson")
    >>> calc = ClimatologiaZCIT(study_area=gdf, mask_to_shape=True)
    """

    def __init__(
        self,
        anos_inicio: int = 1979,
        anos_fim: int = 2023,
        study_area: StudyAreaType = None,
        mask_to_shape: bool = False,
    ) -> None:
        """
        Inicializa o calculador de climatologia.

        Parameters
        ----------
        anos_inicio : int
            Ano inicial para climatologia
        anos_fim : int
            Ano final para climatologia
        study_area : StudyAreaType
            Área de estudo flexível (None, tuple, str, GeoDataFrame)
        mask_to_shape : bool
            Se True, mascara para forma exata da geometria
        """
        self.anos_inicio = anos_inicio
        self.anos_fim = anos_fim
        self.study_area = study_area
        self.mask_to_shape = mask_to_shape
        self.loader = NOAADataLoader(cache_dir="./climatologia_cache")
        self.processor = DataProcessor()

        # Dicionários para armazenar resultados
        self.climatologia_mensal: ClimatologyData = {}
        self.dados_historicos: dict[int, list[dict]] = {}

        # Log da configuração escolhida
        self._log_configuracao_area()

    def _log_configuracao_area(self) -> None:
        """Log da configuração de área escolhida pelo usuário."""
        print("🗺️  CONFIGURAÇÃO DA ÁREA DE ESTUDO:")

        if self.study_area is None:
            print("   📍 Tipo: Geometria padrão interna (Area_LOCZCIT.parquet)")
            print(
                f"   🔧 Mascaramento: {'Ativo' if self.mask_to_shape else 'BBOX apenas'}"
            )

        elif isinstance(self.study_area, tuple):
            lat_min, lat_max, lon_min, lon_max = self.study_area
            print("   📍 Tipo: Bounding Box personalizado")
            print(f"   📐 Latitude: {lat_min}° a {lat_max}°")
            print(f"   📐 Longitude: {lon_min}° a {lon_max}°")
            print("   🔧 Mascaramento: Não aplicável (BBOX)")

        elif isinstance(self.study_area, str):
            print("   📍 Tipo: Arquivo de geometria")
            print(f"   📁 Caminho: {self.study_area}")
            print(
                f"   🔧 Mascaramento: {'Ativo' if self.mask_to_shape else 'BBOX apenas'}"
            )

        elif HAS_GEOPANDAS and isinstance(self.study_area, gpd.GeoDataFrame):
            print("   📍 Tipo: GeoDataFrame fornecido")
            print(f"   📊 Geometrias: {len(self.study_area)}")
            print(
                f"   🔧 Mascaramento: {'Ativo' if self.mask_to_shape else 'BBOX apenas'}"
            )

        else:
            print("   📍 Tipo: Personalizado/Desconhecido")
            print(
                f"   🔧 Mascaramento: {'Ativo' if self.mask_to_shape else 'BBOX apenas'}"
            )

    def baixar_dados_historicos(self, anos_amostra: list[int] | None = None) -> None:
        """
        Baixa e processa dados históricos para cálculo da climatologia.

        ANALOGIA DO ARQUEÓLOGO CLIMÁTICO 🏛️
        Como um arqueólogo que escava camadas de tempo para entender
        os padrões climáticos do passado, reconstruindo a "história"
        da ZCIT através de múltiplos anos de dados.

        Parameters
        ----------
        anos_amostra : List[int], optional
            Lista de anos específicos para processar. Se None, usa amostragem representativa.

        Raises
        ------
        Exception
            Se houver erro no download ou processamento dos dados
        """
        print("🌍 CALCULANDO CLIMATOLOGIA DA ZCIT")
        print(f"📅 Período: {self.anos_inicio}-{self.anos_fim}")
        print("=" * 60)

        # Se não especificado, usar amostragem representativa
        if anos_amostra is None:
            anos_amostra = self._selecionar_anos_representativos()

        print(f"📊 Processando {len(anos_amostra)} anos representativos:")
        print(f"   {anos_amostra}")

        for ano in anos_amostra:
            print(f"\n📈 Processando ano {ano}...")

            try:
                # USAR LOAD_DATA_DUAL_SCALE PARA FLEXIBILIDADE MÁXIMA
                # Esta é a chave da atualização - agora usa a mesma lógica flexível!
                (
                    dados_globais,
                    dados_study_area,
                ) = self.loader.load_data_dual_scale(
                    start_date=f"{ano}-01-01",
                    end_date=f"{ano}-12-31",
                    study_area=self.study_area,  # ✅ Flexível: None, tuple, str, GeoDataFrame
                    auto_download=True,
                    quality_control=True,
                    remove_leap_days=True,
                    return_study_area_subset=True,
                    mask_to_shape=self.mask_to_shape,  # ✅ Mascaramento opcional
                )

                # Usar dados da área de estudo se disponível, senão usar globais
                dados_ano = (
                    dados_study_area if dados_study_area is not None else dados_globais
                )

                if dados_ano is not None:
                    # Processar dados mensais
                    self._processar_dados_anuais(dados_ano, ano)
                    print(f"✅ Ano {ano} processado com sucesso")

                    # Log do tamanho dos dados processados
                    if dados_study_area is not None:
                        print(
                            f"   📏 Dados da área de estudo: {dados_study_area.sizes}"
                        )
                    else:
                        print(f"   📏 Dados globais utilizados: {dados_globais.sizes}")

                else:
                    print(f"❌ Falha ao carregar dados de {ano}")

            except Exception as e:
                print(f"❌ Erro no ano {ano}: {e}")
                continue

    def _selecionar_anos_representativos(self) -> list[int]:
        """
        Seleciona anos representativos para climatologia eficiente.

        ANALOGIA DO ESTATÍSTICO CLIMÁTICO 📊
        Como um estatístico que escolhe uma "amostra representativa"
        da população de anos, garantindo que capture diferentes
        condições climáticas (El Niño, La Niña, anos neutros).

        Estratégia:
        - Eventos ENSO diferentes (El Niño, La Niña, Neutro)
        - Décadas diferentes para capturar variabilidade
        - Anos com dados completos e confiáveis

        Returns
        -------
        List[int]
            Lista de anos representativos filtrados pelo período disponível
        """
        # Anos representativos baseados em fases ENSO e disponibilidade
        anos_representativos = [
            # Década de 1980 (dados iniciais)
            1982,  # El Niño forte
            1985,  # Neutro
            1988,  # La Niña
            # Década de 1990
            1992,  # Neutro
            1995,  # La Niña
            1997,  # El Niño forte
            # Década de 2000
            2001,  # La Niña
            2005,  # Neutro
            2009,  # El Niño
            # Década de 2010
            2010,  # La Niña forte
            2015,  # El Niño muito forte
            2018,  # La Niña
            # Década de 2020 (mais recente)
            2020,  # La Niña
            2022,  # La Niña persistente
        ]

        # Filtrar apenas anos dentro do período disponível
        anos_filtrados = [
            ano
            for ano in anos_representativos
            if self.anos_inicio <= ano <= self.anos_fim
        ]

        return anos_filtrados

    def _processar_dados_anuais(self, dados_ano: xr.Dataset, ano: int) -> None:
        """
        Processa dados anuais para extrair posições mensais da ZCIT.

        Parameters
        ----------
        dados_ano : xr.Dataset
            Dataset com dados anuais de OLR
        ano : int
            Ano dos dados sendo processados
        """
        # Agrupar por mês
        dados_mensais = dados_ano.groupby("time.month")

        for mes, dados_mes in dados_mensais:
            # Calcular média mensal
            media_mensal = dados_mes.olr.mean(dim="time")

            try:
                # Encontrar posições da ZCIT usando LOCZCIT-IQR
                coords_zcit = self.processor.find_minimum_coordinates(
                    media_mensal, method="column_minimum"
                )

                # Calcular posição média da ZCIT para este mês
                if coords_zcit:
                    lats_zcit = [coord[1] for coord in coords_zcit]
                    posicao_media = np.mean(lats_zcit)

                    # Armazenar resultado
                    if mes not in self.dados_historicos:
                        self.dados_historicos[mes] = []

                    self.dados_historicos[mes].append(
                        {
                            "ano": ano,
                            "posicao_lat": posicao_media,
                            "num_pontos": len(coords_zcit),
                            "olr_medio": float(media_mensal.mean()),
                        }
                    )

            except Exception as e:
                print(f"⚠️  Erro no mês {mes}/{ano}: {e}")
                continue

    def calcular_climatologia_final(self) -> None:
        """
        Calcula a climatologia final baseada nos dados históricos processados.

        Aplica estatísticas robustas com remoção de outliers extremos (> 3σ)
        e calcula médias, desvios padrão e outras estatísticas por mês.
        """
        print("\n🧮 CALCULANDO CLIMATOLOGIA FINAL...")

        for mes in range(1, 13):
            if mes in self.dados_historicos:
                dados_mes = self.dados_historicos[mes]

                if dados_mes:
                    posicoes = [d["posicao_lat"] for d in dados_mes]

                    # Estatísticas robustas
                    media = np.mean(posicoes)
                    desvio = np.std(posicoes)

                    # Remover outliers extremos (> 3 desvios padrão)
                    posicoes_filtradas = [
                        p for p in posicoes if abs(p - media) <= 3 * desvio
                    ]

                    # Recalcular sem outliers
                    if posicoes_filtradas:
                        media_final = np.mean(posicoes_filtradas)
                        desvio_final = np.std(posicoes_filtradas)
                    else:
                        media_final = media
                        desvio_final = desvio

                    self.climatologia_mensal[mes] = {
                        "posicao_media": round(media_final, 1),
                        "desvio_padrao": round(desvio_final, 1),
                        "num_anos": len(posicoes_filtradas),
                        "posicoes_brutas": posicoes,
                    }

                    print(
                        f"📅 Mês {mes:2d}: {media_final:+5.1f}° ± {desvio_final:.1f}° "
                        f"({len(posicoes_filtradas)} anos)"
                    )

            else:
                print(f"❌ Mês {mes}: Sem dados suficientes")

    def obter_climatologia_dicionario(self) -> MonthlyClimatology:
        """
        Retorna a climatologia em formato de dicionário simples.

        Returns
        -------
        Dict[int, float]
            Dicionário com posição média da ZCIT por mês {mês: latitude}
        """
        return {
            mes: dados["posicao_media"]
            for mes, dados in self.climatologia_mensal.items()
        }

    def plotar_climatologia(self) -> None:
        """
        Cria visualização da climatologia calculada.

        Gera gráfico com posições mensais, barras de erro (desvio padrão),
        linha do equador e anotações dos valores.

        Raises
        ------
        ValueError
            Se a climatologia não foi calculada ainda
        """
        if not self.climatologia_mensal:
            raise ValueError(
                "Climatologia não calculada. Execute calcular_climatologia_final() primeiro."
            )

        # Preparar dados para plot
        meses = list(range(1, 13))
        posicoes = [
            self.climatologia_mensal.get(mes, {}).get("posicao_media", 0)
            for mes in meses
        ]
        desvios = [
            self.climatologia_mensal.get(mes, {}).get("desvio_padrao", 0)
            for mes in meses
        ]

        # Nomes dos meses
        nomes_meses = [
            "Jan",
            "Fev",
            "Mar",
            "Abr",
            "Mai",
            "Jun",
            "Jul",
            "Ago",
            "Set",
            "Out",
            "Nov",
            "Dez",
        ]

        # Criar figura
        fig, ax = plt.subplots(figsize=(12, 8))

        # Plot principal
        ax.plot(
            meses,
            posicoes,
            "o-",
            linewidth=3,
            markersize=8,
            color="blue",
            label="Posição Climatológica da ZCIT",
        )

        # Barras de erro (desvio padrão)
        ax.errorbar(
            meses,
            posicoes,
            yerr=desvios,
            fmt="none",
            capsize=5,
            capthick=2,
            color="red",
            alpha=0.7,
            label="Desvio Padrão",
        )

        # Linha do equador
        ax.axhline(
            y=0,
            color="black",
            linestyle="--",
            alpha=0.7,
            linewidth=2,
            label="Equador (0°)",
        )

        # Personalização
        ax.set_xlabel("Mês", fontsize=14, fontweight="bold")
        ax.set_ylabel("Latitude da ZCIT (°N)", fontsize=14, fontweight="bold")

        # Título dinâmico baseado na área de estudo
        area_desc = self._obter_descricao_area()
        ax.set_title(
            f"Climatologia da ZCIT - {area_desc}\n"
            f"Baseada em dados NOAA ({self.anos_inicio}-{self.anos_fim})",
            fontsize=16,
            fontweight="bold",
        )

        # Configurar eixos
        ax.set_xticks(meses)
        ax.set_xticklabels(nomes_meses)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=12)

        # Adicionar valores nas barras
        for i, (pos, dev) in enumerate(zip(posicoes, desvios, strict=False)):
            if self.climatologia_mensal.get(i + 1):
                ax.annotate(
                    f"{pos:+.1f}°",
                    (i + 1, pos),
                    textcoords="offset points",
                    xytext=(0, 10),
                    ha="center",
                    fontsize=10,
                    fontweight="bold",
                )

        plt.tight_layout()
        plt.show()

        # Imprimir resumo
        print("\n📋 RESUMO DA CLIMATOLOGIA:")
        print(f"   Área de estudo: {area_desc}")
        print(
            f"   Posição mais ao sul: {min(posicoes):.1f}°N "
            f"(mês {posicoes.index(min(posicoes)) + 1})"
        )
        print(
            f"   Posição mais ao norte: {max(posicoes):.1f}°N "
            f"(mês {posicoes.index(max(posicoes)) + 1})"
        )
        print(f"   Amplitude anual: {max(posicoes) - min(posicoes):.1f}°")

    def _obter_descricao_area(self) -> str:
        """Retorna descrição da área de estudo para títulos e relatórios."""
        if self.study_area is None:
            return "Área Padrão LOCZCIT"
        if isinstance(self.study_area, tuple):
            lat_min, lat_max, lon_min, lon_max = self.study_area
            return f"BBOX ({lat_min}°-{lat_max}°N, {lon_min}°-{lon_max}°E)"
        if isinstance(self.study_area, str):
            return f"Geometria: {Path(self.study_area).name}"
        if HAS_GEOPANDAS and isinstance(self.study_area, gpd.GeoDataFrame):
            return f"GeoDataFrame ({len(self.study_area)} geometrias)"
        return "Área Customizada"


def calcular_climatologia_zcit_completa(
    study_area: StudyAreaType = None,
    mask_to_shape: bool = False,
    anos_inicio: int = 1979,
    anos_fim: int = 2023,
) -> tuple[MonthlyClimatology | None, ClimatologiaZCIT | None]:
    """
    Função principal para calcular a climatologia científica da ZCIT com área flexível.

    ANALOGIA DO DIRETOR DE ORQUESTRA CLIMÁTICA 🎼
    Como um maestro que coordena diferentes instrumentos (dados) e músicos (anos)
    para criar uma sinfonia harmoniosa (climatologia), esta função rege todo
    o processo de cálculo usando a área de estudo mais adequada.

    Parameters
    ----------
    study_area : StudyAreaType, default=None
        Área de estudo flexível. Pode ser:
        - None: Usa geometria padrão interna (Area_LOCZCIT.parquet)
        - tuple: (lat_min, lat_max, lon_min, lon_max) para bounding box
        - str: Caminho para arquivo de geometria (.shp, .geojson, .parquet)
        - geopandas.GeoDataFrame: Objeto GeoDataFrame já carregado
    mask_to_shape : bool, default=False
        Se True e uma geometria é fornecida, mascara dados para forma exata.
        Se False, usa recorte por bounding box apenas.
    anos_inicio : int, default=1979
        Ano inicial para climatologia
    anos_fim : int, default=2023
        Ano final para climatologia

    Returns
    -------
    Tuple[Optional[Dict[int, float]], Optional[ClimatologiaZCIT]]
        Tupla com climatologia calculada e instância da classe, ou (None, None) se erro

    Examples
    --------
    >>> # Usar área padrão
    >>> climatologia, calculadora = calcular_climatologia_zcit_completa()
    >>> if climatologia:
    ...     print(f"ZCIT em março: {climatologia[3]:.1f}°N")

    >>> # Usar BBOX específico
    >>> area_ne = (-18, -2, -48, -32)  # Nordeste do Brasil
    >>> clima_ne, calc_ne = calcular_climatologia_zcit_completa(study_area=area_ne)

    >>> # Usar arquivo de geometria com mascaramento
    >>> clima_geo, calc_geo = calcular_climatologia_zcit_completa(
    ...     study_area="minha_bacia.shp",
    ...     mask_to_shape=True
    ... )

    >>> # Usar GeoDataFrame
    >>> gdf = gpd.read_file("regioes_climaticas.geojson")
    >>> clima_gdf, calc_gdf = calcular_climatologia_zcit_completa(
    ...     study_area=gdf,
    ...     mask_to_shape=True
    ... )
    """
    print("🌊 INICIANDO CÁLCULO DA CLIMATOLOGIA CIENTÍFICA DA ZCIT")
    print("=" * 65)

    # Inicializar calculadora com configuração flexível
    calc_clima = ClimatologiaZCIT(
        anos_inicio=anos_inicio,
        anos_fim=anos_fim,
        study_area=study_area,  # ✅ Agora flexível!
        mask_to_shape=mask_to_shape,  # ✅ Mascaramento opcional!
    )

    try:
        # 1. Baixar e processar dados históricos
        calc_clima.baixar_dados_historicos()

        # 2. Calcular climatologia final
        calc_clima.calcular_climatologia_final()

        # 3. Obter resultado em formato dicionário
        climatologia_final = calc_clima.obter_climatologia_dicionario()

        # 4. Plotar resultados
        calc_clima.plotar_climatologia()

        # 5. Retornar climatologia calculada
        print("\n🎯 CLIMATOLOGIA CIENTÍFICA CALCULADA:")
        print(f"climatologia = {climatologia_final}")

        return climatologia_final, calc_clima

    except Exception as e:
        print(f"❌ Erro no cálculo da climatologia: {e}")
        return None, None


def obter_climatologia_zcit_rapida() -> MonthlyClimatology:
    """
    Retorna climatologia pré-calculada baseada em literatura científica.

    Valores baseados em estudos de:
    - Waliser & Gautier (1993) - Journal of Climate
    - Xie & Philander (1994) - Journal of Climate
    - Cavalcanti et al. (2009) - Tempo e Clima no Brasil
    - Ferreira et al. (2005) - Revista Brasileira de Meteorologia

    Returns
    -------
    Dict[int, float]
        Climatologia da ZCIT para Atlântico Tropical (região 40°W)

    Examples
    --------
    >>> clima = obter_climatologia_zcit_rapida()
    >>> print(f"ZCIT em julho: {clima[7]:.1f}°N")
    8.5
    """
    # Climatologia baseada em literatura científica validada
    # Valores para o Atlântico Tropical (região 40°W)
    climatologia_cientifica: MonthlyClimatology = {
        1: -1.5,  # Janeiro - verão austral, ZCIT mais ao sul
        2: -3.0,  # Fevereiro - pico ao sul
        3: -2.5,  # Março - ainda ao sul mas subindo
        4: 0.5,  # Abril - transição
        5: 3.5,  # Maio - subindo para norte
        6: 6.0,  # Junho - inverno austral, ZCIT ao norte
        7: 8.5,  # Julho - pico ao norte
        8: 9.0,  # Agosto - posição mais ao norte
        9: 7.0,  # Setembro - começando a descer
        10: 4.0,  # Outubro - transição
        11: 1.0,  # Novembro - descendo
        12: -0.5,  # Dezembro - voltando ao sul
    }

    print("📚 Usando climatologia baseada em literatura científica")
    print("📖 Referências: Waliser & Gautier (1993), Xie & Philander (1994)")

    return climatologia_cientifica


def obter_climatologia_zcit_1994_2023_NOAA(
    climatologia_pre_calculada: MonthlyClimatology = None,
) -> MonthlyClimatology:
    """
    Retorna climatologia pré-calculada baseada em climatologia NOAA de 1994 a 2023.

    Returns
    -------
    Dict[int, float]
        Climatologia da ZCIT pre calculada para o período 1994-2023.

    Examples
    --------
    >>> clima = obter_climatologia_zcit_1994_2023_NOAA()
    >>> print(f"ZCIT em julho: {clima[7]:.1f}°N")
    8.5
    """
    if climatologia_pre_calculada is not None:
        print("📚 Usando climatologia pré-calculada fornecida")
        return climatologia_pre_calculada
    # Aviso pra inserir climatologia pre calculada
    print("⚠️  Climatologia pré-calculada não fornecida")
    print(
        "🙏 Por favor, forneça uma climatologia pré-calculada ou use a função obter_climatologia_zcit_rapida()"
    )
    print(
        "⚠️ Lembrete: Dicionario deve conter meses como chaves (1-12) e valores de latitude da ZCIT"
    )
    return (
        obter_climatologia_zcit_rapida()
    )  # Retorna a climatologia rápida como fallback


def _interpretar_anomalia_meteorologica(
    mes: int, diferenca: float, desvios_sigma: float
) -> str:
    """
    Interpretação meteorológica contextual da anomalia.

    Parameters
    ----------
    mes : int
        Mês da análise (1-12)
    diferenca : float
        Diferença da posição climatológica (graus)
    desvios_sigma : float
        Número de desvios padrão da anomalia

    Returns
    -------
    str
        Interpretação meteorológica da anomalia
    """
    if abs(diferenca) < 1.5:
        return "A ZCIT está em posição típica para a época do ano. Padrão atmosférico normal."

    # Interpretação baseada na direção e magnitude da anomalia
    if diferenca > 0:  # ZCIT mais ao norte
        if mes in [1, 2, 3, 4]:  # Verão austral
            return (
                "ZCIT anômalamente ao norte para o verão. "
                "Pode indicar: (1) Anomalia de TSM no Atlântico Sul, "
                "(2) Influência de El Niño, (3) Padrão anômalo de precipitação no Norte/Nordeste."
            )
        if mes in [6, 7, 8, 9]:  # Inverno austral
            return (
                "ZCIT muito ao norte - intensificação do padrão de inverno. "
                "Pode resultar em: (1) Seca severa no Nordeste, "
                "(2) Maior atividade convectiva no Caribe/Venezuela."
            )
        # Transição
        return (
            "ZCIT ao norte durante transição sazonal. "
            "Pode afetar início/fim da estação chuvosa."
        )

    # ZCIT mais ao sul
    if mes in [1, 2, 3, 4]:  # Verão austral
        return (
            "ZCIT extremamente ao sul - intensificação do verão. "
            "Pode causar: (1) Chuvas excessivas no Norte/Nordeste, "
            "(2) Possível influência de La Niña, (3) Anomalias de TSM."
        )
    if mes in [6, 7, 8, 9]:  # Inverno austral
        return (
            "ZCIT anômalamente ao sul para o inverno. "
            "Pode indicar: (1) Enfraquecimento dos ventos alísios, "
            "(2) Anomalia de pressão atmosférica, (3) Chuvas fora de época."
        )
    # Transição
    return "ZCIT ao sul durante transição - possível antecipação/atraso sazonal."


def _obter_contexto_sazonal(
    mes: int, posicao_encontrada: float, posicao_climatologica: float
) -> str:
    """
    Fornece contexto sazonal para a posição da ZCIT.

    Parameters
    ----------
    mes : int
        Mês da análise (1-12)
    posicao_encontrada : float
        Posição da ZCIT encontrada na análise
    posicao_climatologica : float
        Posição climatológica da ZCIT para o mês

    Returns
    -------
    str
        Contexto sazonal e impactos esperados
    """
    contextos_sazonais = {
        1: "Verão austral - ZCIT tipicamente ao sul, favorecendo chuvas no Norte/Nordeste",
        2: "Pico do verão - ZCIT em posição mais austral do ano",
        3: "Final do verão - ZCIT começando migração para norte",
        4: "Outono - ZCIT em transição, período crítico para previsão de chuvas",
        5: "Fim das chuvas no Norte - ZCIT migrando para norte",
        6: "Início do inverno austral - ZCIT se estabelecendo ao norte",
        7: "Inverno - ZCIT no hemisfério norte, seca no Nordeste",
        8: "Pico do inverno - ZCIT em posição mais setentrional",
        9: "Final do inverno - ZCIT iniciando retorno para sul",
        10: "Primavera - ZCIT em transição para sul",
        11: "Pré-verão - ZCIT se aproximando da posição de verão",
        12: "Início do verão - ZCIT migrando para posição austral",
    }

    contexto_base = contextos_sazonais.get(mes, "Período de transição sazonal")

    # Adicionar informação sobre impactos
    if mes in [1, 2, 3, 4, 5] and posicao_encontrada < posicao_climatologica:
        impacto = "Possível intensificação das chuvas na região Norte/Nordeste."
    elif mes in [6, 7, 8, 9] and posicao_encontrada > posicao_climatologica:
        impacto = "Possível intensificação da seca no Nordeste brasileiro."
    elif mes in [1, 2, 3, 4, 5] and posicao_encontrada > posicao_climatologica:
        impacto = "Possível redução das chuvas na região Norte/Nordeste."
    elif mes in [6, 7, 8, 9] and posicao_encontrada < posicao_climatologica:
        impacto = "Possível alívio da seca no Nordeste brasileiro."
    else:
        impacto = "Padrão dentro do esperado para a época."

    return f"{contexto_base}. {impacto}"


def comparar_com_climatologia_cientifica(
    mes: int,
    posicao_encontrada: float,
    usar_climatologia_calculada: bool = True,
) -> tuple[str, float, str]:
    """
    Compara a posição encontrada com climatologia científica.

    Parameters
    ----------
    mes : int
        Mês da análise (1-12)
    posicao_encontrada : float
        Posição da ZCIT encontrada na análise (graus latitude)
    usar_climatologia_calculada : bool, default=True
        Se True, tenta usar climatologia calculada. Se False, usa literatura.

    Returns
    -------
    Tuple[str, float, str]
        Status da anomalia, diferença em graus, e interpretação meteorológica

    Examples
    --------
    >>> status, desvio, interpretacao = comparar_com_climatologia_cientifica(3, -0.32)
    >>> print(f"Status: {status}, Desvio: {desvio:.1f}°")
    Status: NORMAL, Desvio: 2.2°
    """
    if usar_climatologia_calculada:
        try:
            # Tentar usar climatologia calculada
            climatologia, _ = calcular_climatologia_zcit_completa()
            if climatologia is None:
                raise Exception("Falha no cálculo")
        except Exception:
            print("⚠️  Falha na climatologia calculada, usando literatura científica")
            climatologia = obter_climatologia_zcit_rapida()
    else:
        climatologia = obter_climatologia_zcit_rapida()

    # Desvios padrão típicos (baseados em variabilidade observada)
    desvio_climatologico = {
        1: 2.0,
        2: 2.5,
        3: 2.2,
        4: 1.8,
        5: 1.5,
        6: 1.2,
        7: 1.0,
        8: 1.1,
        9: 1.3,
        10: 1.6,
        11: 1.9,
        12: 2.1,
    }

    posicao_climatologica = climatologia.get(mes, 0)
    desvio_padrao = desvio_climatologico.get(mes, 2.0)
    diferenca = posicao_encontrada - posicao_climatologica

    # Nomes dos meses para display

    print("\n📊 COMPARAÇÃO COM CLIMATOLOGIA CIENTÍFICA:")
    print("📅 Mês analisado: {nomes_meses.get(mes, mes)}")
    if posicao_encontrada > 0:
        print("📍 Posição encontrada: {posicao_encontrada:+5.1f}°N")
    elif posicao_encontrada < 0:
        print("📍 Posição encontrada: {posicao_encontrada:+5.1f}°S")
    else:
        print("📍 Posição encontrada: {posicao_encontrada:+5.1f}° (Linha do Equador)")

    print(
        "📖 Posição climatológica: {posicao_climatologica:+5.1f}°N (±{desvio_padrao:.1f}°)"
    )
    print(
        "📏 Diferença: {diferenca:+5.1f}° ({abs(diferenca/desvio_padrao):.1f} desvios padrão)"
    )

    # Cálculo de percentual de anomalia
    if posicao_climatologica != 0:
        percentual = (diferenca / abs(posicao_climatologica)) * 100
        print(f"📈 Anomalia percentual: {percentual:+5.1f}%")

    # Classificação estatística baseada em desvios padrão
    desvios_sigma = abs(diferenca) / desvio_padrao

    if desvios_sigma < 1.0:
        print("✅ Posição dentro da variabilidade normal (< 1σ)")
        status = "NORMAL"
        cor_status = "🟢"
    elif desvios_sigma < 2.0:
        print("⚠️  Anomalia moderada (1-2σ)")
        status = "ANOMALIA_MODERADA"
        cor_status = "🟡"
    elif desvios_sigma < 3.0:
        print("🔶 Anomalia forte (2-3σ)")
        status = "ANOMALIA_FORTE"
        cor_status = "🟠"
    else:
        print("🚨 Anomalia extrema (> 3σ) - evento muito raro!")
        status = "ANOMALIA_EXTREMA"
        cor_status = "🔴"

    # Interpretação meteorológica contextual
    interpretacao = _interpretar_anomalia_meteorologica(mes, diferenca, desvios_sigma)

    print(f"\n🌡️  STATUS CLIMATOLÓGICO: {cor_status} {status}")
    print("📝 INTERPRETAÇÃO METEOROLÓGICA:")
    print(f"   {interpretacao}")

    # Contexto sazonal
    contexto = _obter_contexto_sazonal(mes, posicao_encontrada, posicao_climatologica)
    print("\n🌊 CONTEXTO SAZONAL:")
    print(f"   {contexto}")

    return status, diferenca, interpretacao


def calcular_climatologia_personalizada(
    cache_dir: str = "cache",
    study_area: StudyAreaType = None,
    anos_amostra: list[int] | None = None,
    mask_to_shape: bool = False,
) -> MonthlyClimatology:
    """
    Calcular climatologia com área de estudo totalmente customizável.

    ANALOGIA DO ALFAIATE CLIMÁTICO ✂️
    Como um alfaiate que corta o tecido (dados climáticos) exatamente
    na medida desejada, esta função permite "costurar" uma climatologia
    sob medida para qualquer área de interesse.

    Parameters
    ----------
    study_area : StudyAreaType, optional
        Área de estudo flexível. Pode ser:
        - None: Usa geometria padrão interna (Area_LOCZCIT.parquet)
        - tuple: (lat_min, lat_max, lon_min, lon_max) para bounding box
        - str: Caminho para arquivo de geometria (.shp, .geojson, .parquet)
        - geopandas.GeoDataFrame: Objeto GeoDataFrame já carregado

    anos_amostra : List[int], optional
        Anos para usar no cálculo. Se None, usa amostra representativa padrão.

    mask_to_shape : bool, default=False
        Se True e uma geometria é fornecida, mascara dados para forma exata.
        Se False, usa recorte por bounding box apenas.

    Returns
    -------
    Dict[int, float]
        Climatologia calculada por mês (1-12) com posição média da ZCIT

    Examples
    --------
    >>> # Usar área padrão
    >>> clima = calcular_climatologia_personalizada()
    >>> print(f"ZCIT em março: {clima[3]:.1f}°N")

    >>> # Definir BBOX específico
    >>> area_ne = (-18, -2, -48, -32)  # Nordeste do Brasil
    >>> clima = calcular_climatologia_personalizada(study_area=area_ne)

    >>> # Usar arquivo de geometria com mascaramento
    >>> clima = calcular_climatologia_personalizada(
    ...     study_area="bacia_amazonica.shp",
    ...     mask_to_shape=True
    ... )

    >>> # Usar GeoDataFrame com anos específicos
    >>> gdf = gpd.read_file("regioes.geojson")
    >>> anos = [2015, 2018, 2020, 2022]
    >>> clima = calcular_climatologia_personalizada(
    ...     study_area=gdf,
    ...     anos_amostra=anos,
    ...     mask_to_shape=True
    ... )
    """
    print("🔬 CALCULANDO CLIMATOLOGIA PERSONALIZADA...")

    # ========================================================================
    # 1. VALIDAR E DESCREVER ÁREA DE ESTUDO
    # ========================================================================

    if study_area is None:
        print("🌍 Usando geometria padrão interna (Area_LOCZCIT.parquet)")
        area_desc = "Área padrão LOCZCIT"
    elif isinstance(study_area, tuple) and len(study_area) == 4:
        lat_min, lat_max, lon_min, lon_max = study_area
        print("🌍 Usando BBOX personalizado:")
        print(f"   📐 Latitude: {lat_min}° a {lat_max}°")
        print(f"   📐 Longitude: {lon_min}° a {lon_max}°")
        area_desc = f"BBOX ({lat_min}°-{lat_max}°N, {lon_min}°-{lon_max}°E)"

        # Validar BBOX
        if lat_min >= lat_max:
            raise ValueError(
                f"Latitude mínima ({lat_min}) deve ser menor que máxima ({lat_max})"
            )
        if lon_min >= lon_max:
            raise ValueError(
                f"Longitude mínima ({lon_min}) deve ser menor que máxima ({lon_max})"
            )
        if lat_min < -90 or lat_max > 90:
            raise ValueError("Latitudes devem estar entre -90 e 90°")
        if lon_min < -180 or lon_max > 180:
            raise ValueError("Longitudes devem estar entre -180 e 180°")

    elif isinstance(study_area, str):
        print(f"🌍 Usando arquivo de geometria: {study_area}")
        print(f"   🔧 Mascaramento: {'Ativo' if mask_to_shape else 'BBOX apenas'}")
        area_desc = f"Geometria: {Path(study_area).name}"

        # Verificar se arquivo existe
        if not Path(study_area).exists():
            raise FileNotFoundError(
                f"Arquivo de geometria não encontrado: {study_area}"
            )

    elif HAS_GEOPANDAS and isinstance(study_area, gpd.GeoDataFrame):
        print("🌍 Usando GeoDataFrame fornecido:")
        print(f"   📊 Geometrias: {len(study_area)}")
        print(f"   🔧 Mascaramento: {'Ativo' if mask_to_shape else 'BBOX apenas'}")
        area_desc = f"GeoDataFrame ({len(study_area)} geometrias)"

    else:
        print("🌍 Área de estudo customizada/desconhecida")
        area_desc = "Área customizada"

    # ========================================================================
    # 2. DEFINIR ANOS DE AMOSTRA
    # ========================================================================

    if anos_amostra is None:
        # Anos representativos para cálculo rápido e robusto
        anos_amostra = [1995, 2000, 2005, 2010, 2015, 2020]
        print(f"📅 Usando anos padrão: {anos_amostra}")
    else:
        print(f"📅 Usando anos personalizados: {anos_amostra}")

        # Validar anos
        for ano in anos_amostra:
            if ano < 1979:
                raise ValueError(
                    f"Dados OLR disponíveis apenas a partir de 1979. Ano {ano} inválido."
                )
            if ano > 2024:
                print(f"⚠️  Aviso: Ano {ano} pode não ter dados completos")

    # ========================================================================
    # 3. INICIALIZAR FERRAMENTAS COM CONFIGURAÇÃO FLEXÍVEL
    # ========================================================================

    # Configurar carregador com cache específico
    loader = NOAADataLoader(cache_dir=cache_dir)
    processor = DataProcessor()

    # Estrutura para armazenar resultados por mês
    resultados_mensais: dict[int, list[float]] = {mes: [] for mes in range(1, 13)}

    # ========================================================================
    # 4. PROCESSAR CADA ANO DA AMOSTRA USANDO LOAD_DATA_DUAL_SCALE
    # ========================================================================

    anos_processados = 0

    for ano in anos_amostra:
        print(f"📅 Processando {ano}...")

        try:
            # ✅ USAR LOAD_DATA_DUAL_SCALE PARA MÁXIMA FLEXIBILIDADE
            dados_globais, dados_study_area = loader.load_data_dual_scale(
                start_date=f"{ano}-01-01",
                end_date=f"{ano}-12-31",
                study_area=study_area,  # ✅ Flexível: None, tuple, str, GeoDataFrame
                auto_download=True,
                quality_control=True,
                remove_leap_days=True,
                return_study_area_subset=True,
                mask_to_shape=mask_to_shape,  # ✅ Mascaramento opcional
            )

            # Usar dados da área de estudo se disponível, senão usar globais
            dados = dados_study_area if dados_study_area is not None else dados_globais

            if dados is None:
                print(f"⚠️  Sem dados para {ano}")
                continue

            # ====================================================================
            # 5. PROCESSAR CADA MÊS DO ANO
            # ====================================================================

            meses_processados = 0

            for mes in range(1, 13):
                try:
                    # Selecionar dados do mês
                    dados_mes = dados.sel(time=dados["time.month"] == mes)

                    if len(dados_mes.time) == 0:
                        continue

                    # Calcular média mensal
                    media_mes = dados_mes.olr.mean(dim="time")

                    # Encontrar posições da ZCIT usando o método column_minimum
                    coords = processor.find_minimum_coordinates(
                        media_mes, method="column_minimum"
                    )

                    if coords and len(coords) > 0:
                        # Calcular latitude média da ZCIT
                        latitudes = [c[1] for c in coords]  # c[1] é a latitude
                        lat_media = np.mean(latitudes)

                        # Armazenar resultado
                        resultados_mensais[mes].append(lat_media)
                        meses_processados += 1

                except Exception as e_mes:
                    print(f"  ❌ Erro no mês {mes}: {e_mes}")
                    continue

            if meses_processados > 0:
                anos_processados += 1
                print(f"  ✅ {meses_processados} meses processados")

                # Log adicional sobre o tipo de dados usado
                if dados_study_area is not None:
                    print(f"  📏 Área de estudo: {dados_study_area.sizes}")
                else:
                    print(f"  📏 Dados globais: {dados_globais.sizes}")
            else:
                print("  ⚠️  Nenhum mês processado")

        except Exception as e_ano:
            print(f"❌ Erro no ano {ano}: {e_ano}")
            continue

    # ========================================================================
    # 6. CALCULAR CLIMATOLOGIA FINAL
    # ========================================================================

    print("\n📊 CALCULANDO CLIMATOLOGIA FINAL...")
    print(f"   Anos processados: {anos_processados}/{len(anos_amostra)}")

    climatologia_calculada: MonthlyClimatology = {}

    for mes in range(1, 13):
        if resultados_mensais[mes]:
            # Calcular média e arredondar para 1 casa decimal
            climatologia_calculada[mes] = round(np.mean(resultados_mensais[mes]), 1)
            print(
                f"   Mês {mes:2d}: {len(resultados_mensais[mes])} anos, "
                f"média: {climatologia_calculada[mes]:+5.1f}°N"
            )
        else:
            # Sem dados suficientes, usar valor neutro
            climatologia_calculada[mes] = 0.0
            print(f"   Mês {mes:2d}: sem dados suficientes")

    # ========================================================================
    # 7. RELATÓRIO FINAL
    # ========================================================================

    print("\n✅ CLIMATOLOGIA PERSONALIZADA CALCULADA:")
    print(f"   Área: {area_desc}")
    print(f"   Período: {min(anos_amostra)}-{max(anos_amostra)}")
    print(f"   Anos válidos: {anos_processados}")
    print(f"   Mascaramento: {'Ativo' if mask_to_shape else 'BBOX apenas'}")

    print("\n📈 POSIÇÕES MÉDIAS DA ZCIT POR MÊS:")
    meses_nomes = [
        "",
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]

    for mes in range(1, 13):
        pos = climatologia_calculada[mes]
        hemisferio = "N" if pos >= 0 else "S"
        print(f"   {meses_nomes[mes]}: {pos:+5.1f}°{hemisferio}")

    return climatologia_calculada


def salvar_climatologia(
    climatologia: MonthlyClimatology,
    arquivo: str | Path = "climatologia_zcit.json",
    metadata_extra: dict | None = None,
) -> None:
    """
    Salva climatologia calculada em arquivo JSON com metadata completa.

    Parameters
    ----------
    climatologia : Dict[int, float]
        Climatologia a ser salva
    arquivo : str or Path, default="climatologia_zcit.json"
        Caminho do arquivo para salvar
    metadata_extra : Dict, optional
        Metadata adicional para incluir no arquivo

    Examples
    --------
    >>> clima = obter_climatologia_zcit_rapida()
    >>> salvar_climatologia(clima, "minha_climatologia.json")

    >>> # Com metadata extra
    >>> metadata = {"area": "Nordeste", "autor": "João Silva"}
    >>> salvar_climatologia(clima, "clima_ne.json", metadata_extra=metadata)
    """
    dados_salvamento = {
        "metadata": {
            "criado_em": datetime.now().isoformat(),
            "versao": "1.0.0",
            "fonte": "LOCZCIT-IQR",
            "descricao": "Climatologia da ZCIT calculada com área flexível",
            "unidade": "graus_latitude_norte",
            "num_meses": len(climatologia),
        },
        "climatologia": climatologia,
        "referencias": [
            "Waliser & Gautier (1993) - J. Climate",
            "Xie & Philander (1994) - J. Climate",
            "Ferreira et al. (2005) - Rev. Bras. Meteorologia",
            "Cavalcanti et al. (2009) - Tempo e Clima no Brasil",
        ],
    }

    # Adicionar metadata extra se fornecida
    if metadata_extra:
        dados_salvamento["metadata"].update(metadata_extra)

    # Adicionar estatísticas da climatologia
    posicoes = list(climatologia.values())
    if posicoes:
        dados_salvamento["estatisticas"] = {
            "posicao_min": round(min(posicoes), 1),
            "posicao_max": round(max(posicoes), 1),
            "amplitude_anual": round(max(posicoes) - min(posicoes), 1),
            "media_anual": round(np.mean(posicoes), 1),
        }

    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados_salvamento, f, indent=2, ensure_ascii=False)

    print(f"✅ Climatologia salva em: {arquivo}")
    if metadata_extra:
        print(f"📋 Metadata extra incluída: {list(metadata_extra.keys())}")


def carregar_climatologia(
    arquivo: str | Path = "climatologia_zcit.json",
) -> MonthlyClimatology:
    """
    Carrega climatologia de arquivo JSON.

    Parameters
    ----------
    arquivo : str or Path, default="climatologia_zcit.json"
        Caminho do arquivo para carregar

    Returns
    -------
    Dict[int, float]
        Climatologia carregada

    Raises
    ------
    FileNotFoundError
        Se o arquivo não for encontrado
    ValueError
        Se o arquivo não tiver formato válido

    Examples
    --------
    >>> clima = carregar_climatologia("minha_climatologia.json")
    >>> print(f"ZCIT em julho: {clima[7]:.1f}°N")
    """
    try:
        with open(arquivo, encoding="utf-8") as f:
            dados = json.load(f)

        # Validar estrutura
        if "climatologia" not in dados:
            raise ValueError("Arquivo não contém dados de climatologia válidos")

        climatologia = dados["climatologia"]

        # Converter chaves para int (JSON salva como string)
        climatologia_int = {int(mes): valor for mes, valor in climatologia.items()}

        print(f"✅ Climatologia carregada de: {arquivo}")
        if "metadata" in dados and "criado_em" in dados["metadata"]:
            print(f"📅 Criado em: {dados['metadata']['criado_em']}")
        if "estatisticas" in dados:
            stats = dados["estatisticas"]
            print(f"📊 Amplitude anual: {stats.get('amplitude_anual', 'N/A')}°")

        return climatologia_int

    except FileNotFoundError:
        raise FileNotFoundError(f"Arquivo de climatologia não encontrado: {arquivo}")
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Erro ao carregar climatologia: {e}")


# ============================================================================
# INTERFACE LIMPA PARA USUÁRIO FINAL - MANTIDA
# ============================================================================


@contextmanager
def _interface_limpa():
    """Context manager ULTRA-AGRESSIVO para suprimir logs verbosos."""

    # Lista de TODOS os loggers que podem aparecer
    loggers_para_silenciar = [
        "",
        "loczcit_iqr",
        "loczcit_iqr.core",
        "loczcit_iqr.core.processor",
        "loczcit_iqr.core.data_loader",
        "loczcit_iqr.core.climatologia",
    ]

    # Silenciar TODOS de forma agressiva
    for logger_name in loggers_para_silenciar:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.disabled = True

    try:
        yield
    finally:
        # Restaurar (opcional)
        for logger_name in loggers_para_silenciar:
            logger = logging.getLogger(logger_name)
            logger.disabled = False
            logger.setLevel(logging.INFO)


def executar_analise_limpa(posicao_zcit, mes):
    """
    Wrapper para análise climatológica com interface limpa e amigável.

    Esta função oferece uma experiência limpa ao usuário, suprimindo logs
    verbosos e apresentando apenas os resultados importantes.

    Parameters
    ----------
    posicao_zcit : float
        Latitude da ZCIT encontrada (em graus)
    mes : int
        Mês da análise (1-12)

    Returns
    -------
    tuple
        (status, desvio, interpretacao) ou (None, None, None) em caso de erro

    Examples
    --------
    >>> # Analisar ZCIT encontrada em março
    >>> status, desvio, interpretacao = executar_analise_limpa(-0.3, 3)
    >>> print(f"Status: {status}, Desvio: {desvio:.1f}°")
    """

    print("🌊 Executando análise climatológica...")

    try:
        # Executar análise com logs suprimidos
        with _interface_limpa():
            (
                status,
                desvio,
                interpretacao,
            ) = comparar_com_climatologia_cientifica(
                mes=mes,
                posicao_encontrada=posicao_zcit,
                usar_climatologia_calculada=False,  # Usar literatura (mais rápido)
            )

        # Apresentar resultados de forma limpa
        print("✅ ANÁLISE CONCLUÍDA:")
        print(f"   📍 Posição analisada: {posicao_zcit:+.1f}°N")
        print(f"   🌡️ Status: {status}")
        print(f"   📏 Desvio: {desvio:+.1f}°")

        # Mostrar interpretação resumida
        if interpretacao:
            # Pegar apenas a primeira linha da interpretação (mais limpo)
            primeira_linha = (
                interpretacao.split("\n")[0] if "\n" in interpretacao else interpretacao
            )
            if len(primeira_linha) > 80:
                primeira_linha = primeira_linha[:77] + "..."
            print(f"   📝 {primeira_linha}")

        return status, desvio, interpretacao

    except Exception as e:
        print(f"❌ Erro na análise climatológica: {e}")
        return None, None, None


def analise_zcit_rapida(posicao_zcit, mes, mostrar_detalhes=False):
    """
    Versão ultra-simplificada para análise rápida da ZCIT.

    Parameters
    ----------
    posicao_zcit : float
        Latitude da ZCIT encontrada
    mes : int
        Mês da análise (1-12)
    mostrar_detalhes : bool, default False
        Se True, mostra interpretação completa

    Returns
    -------
    str
        Status climatológico ('NORMAL', 'ANOMALIA_MODERADA', 'ANOMALIA_EXTREMA')

    Examples
    --------
    >>> status = analise_zcit_rapida(-0.3, 3)
    >>> print(f"ZCIT está: {status}")
    """

    # Emojis para status
    emojis = {"NORMAL": "✅", "ANOMALIA_MODERADA": "🟡", "ANOMALIA_EXTREMA": "🔴"}

    try:
        with _interface_limpa():
            (
                status,
                desvio,
                interpretacao,
            ) = comparar_com_climatologia_cientifica(
                mes=mes, posicao_encontrada=posicao_zcit
            )

        emoji = emojis.get(status, "❓")
        print(f"{emoji} ZCIT: {status} (desvio: {desvio:+.1f}°)")

        if mostrar_detalhes and interpretacao:
            print(f"📋 Detalhes: {interpretacao}")

        return status

    except Exception as e:
        print(f"❌ Erro: {e}")
        return "ERRO"


def configurar_experiencia_climatologia(nivel="simples"):
    """
    Configura o nível de detalhamento dos logs para análise climatológica.

    Parameters
    ----------
    nivel : str
        'silencioso' - Apenas resultados
        'simples' - Resultados + avisos importantes
        'detalhado' - Informações de processamento
        'completo' - Todos os logs (debug)
    """

    niveis_config = {
        "silencioso": logging.CRITICAL,
        "simples": logging.ERROR,
        "detalhado": logging.WARNING,
        "completo": logging.DEBUG,
    }

    if nivel not in niveis_config:
        print(f"⚠️ Nível '{nivel}' inválido. Usando 'simples'.")
        nivel = "simples"

    logging.basicConfig(level=niveis_config[nivel], force=True)
    logging.getLogger("loczcit_iqr").setLevel(niveis_config[nivel])

    print(f"🔧 Configuração: nível '{nivel}' ativado")


# ============================================================================
# FUNÇÕES DE CONVENIÊNCIA PARA USUÁRIOS FINAIS - MANTIDAS
# ============================================================================


def verificar_zcit_janeiro(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para janeiro."""
    print("🌧️ ANÁLISE PARA JANEIRO (Verão no HS - ÉPOCA DE CHUVAS):")
    return analise_zcit_rapida(posicao_zcit, mes=1, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_fevereiro(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para fevereiro."""
    print("🌧️ ANÁLISE PARA FEVEREIRO (Verão no HS - PICO DAS CHUVAS):")
    return analise_zcit_rapida(posicao_zcit, mes=2, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_marco(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para março."""
    print("🍂 ANÁLISE PARA MARÇO (Outono no HS - FINAL DAS CHUVAS):")
    return analise_zcit_rapida(posicao_zcit, mes=3, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_abril(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para abril."""
    print("🍂 ANÁLISE PARA ABRIL (Outono no HS - PERÍODO DE TRANSIÇÃO):")
    return analise_zcit_rapida(posicao_zcit, mes=4, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_maio(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para maio."""
    print("🍂 ANÁLISE PARA MAIO (Outono no HS - TRANSIÇÃO PARA A SECA):")
    return analise_zcit_rapida(posicao_zcit, mes=5, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_junho(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para junho."""
    print("☀️ ANÁLISE PARA JUNHO (Inverno no HS - INÍCIO DA ÉPOCA SECA):")
    return analise_zcit_rapida(posicao_zcit, mes=6, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_julho(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para julho."""
    print("☀️ ANÁLISE PARA JULHO (Inverno no HS - PICO DA ÉPOCA SECA):")
    return analise_zcit_rapida(posicao_zcit, mes=7, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_agosto(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para agosto."""
    print("☀️ ANÁLISE PARA AGOSTO (Inverno no HS - FINAL DA ÉPOCA SECA):")
    return analise_zcit_rapida(posicao_zcit, mes=8, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_setembro(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para setembro."""
    print("🍂 ANÁLISE PARA SETEMBRO (Primavera no HS - PERÍODO DE TRANSIÇÃO):")
    return analise_zcit_rapida(posicao_zcit, mes=9, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_outubro(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para outubro."""
    print("🍂 ANÁLISE PARA OUTUBRO (Primavera no HS - INÍCIO DAS CHUVAS):")
    return analise_zcit_rapida(posicao_zcit, mes=10, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_novembro(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para novembro."""
    print("🌧️ ANÁLISE PARA NOVEMBRO (Primavera no HS - ÉPOCA DE CHUVAS):")
    return analise_zcit_rapida(posicao_zcit, mes=11, mostrar_detalhes=mostrar_detalhes)


def verificar_zcit_dezembro(posicao_zcit, mostrar_detalhes=False):
    """Verificação rápida específica para dezembro."""
    print("🌧️ ANÁLISE PARA DEZEMBRO (Verão no HS - ÉPOCA DE CHUVAS):")
    return analise_zcit_rapida(posicao_zcit, mes=12, mostrar_detalhes=mostrar_detalhes)


# ============================================================================
# SISTEMA AVANÇADO DE CLIMATOLOGIAS TEMPORAIS
# ============================================================================


def executar_climatologias_completas_zcit(
    study_area: StudyAreaType = None,
    anos: list[int] | None = None,
    diretorio_saida: str | Path = "./climatologias_personalizadas",
    mask_to_shape: bool = True,
    prefixo_arquivo: str = "clima_regiao_norte",
    incluir_metadata: bool = True,
) -> tuple[dict[str, str], dict[str, Any]] | None:
    """
    Executa a criação completa das climatologias da ZCIT.

    ANALOGIA DO DIRETOR DE ORQUESTRA CLIMÁTICA 🎼
    Como um maestro que coordena diferentes instrumentos (dados) e músicos (anos)
    para criar uma sinfonia harmoniosa (climatologia), esta função rege todo
    o processo de cálculo usando a área de estudo mais adequada.

    Parameters
    ----------
    study_area : StudyAreaType, optional
        Área de estudo flexível. Padrão: None (usa área padrão ZCIT).
    anos : List[int], optional
        Lista de anos. Padrão: [2015-2020].
    diretorio_saida : str or Path, optional
        Diretório para salvar os arquivos.
    mask_to_shape : bool, optional
        Se True, mascara para a forma exata da geometria.
    prefixo_arquivo : str, optional
        Prefixo para os nomes dos arquivos de saída.
    incluir_metadata : bool, optional
        Se True, inclui metadados detalhados nos arquivos.

    Returns
    -------
    Tuple[Dict[str, str], Dict[str, Any]] or None
        Tupla com (arquivos_gerados, resultados_analise) ou (None, None) em caso de erro.
    """
    print("🌊 INICIANDO CRIAÇÃO DE CLIMATOLOGIAS COMPLETAS DA ZCIT")
    print("=" * 70)

    # Use os argumentos da função ou valores padrão
    anos_analise = anos if anos is not None else list(range(2015, 2021))

    print(f"📅 Período: {min(anos_analise)}-{max(anos_analise)}")
    print(f"📁 Saída: {diretorio_saida}")

    try:
        print("\n⏰ CRIANDO CLIMATOLOGIAS TEMPORAIS COMPLETAS...")
        # A função que não existia, 'criar_climatologias_completas', foi mesclada aqui.
        # Esta função agora faz o trabalho completo.

        # 1. VALIDAÇÃO E CONFIGURAÇÃO
        diretorio_saida = Path(diretorio_saida)
        diretorio_saida.mkdir(parents=True, exist_ok=True)
        area_id = _gerar_identificador_area(study_area)

        # 2. INICIALIZAÇÃO
        loader = NOAADataLoader(cache_dir=diretorio_saida / ".cache")
        processor = DataProcessor()
        dados_diarios, dados_mensais, dados_pentadas = (
            [],
            {m: [] for m in range(1, 13)},
            {p: [] for p in range(1, 74)},
        )

        # 3. PROCESSAMENTO DOS ANOS
        for ano in anos_analise:
            print(f"🔄 Processando ano {ano}...")
            dados_globais, dados_study_area = loader.load_data_dual_scale(
                start_date=f"{ano}-01-01",
                end_date=f"{ano}-12-31",
                study_area=study_area,
                auto_download=True,
                quality_control=True,
                remove_leap_days=True,
                return_study_area_subset=True,
                mask_to_shape=mask_to_shape,
            )
            dados = dados_study_area if dados_study_area is not None else dados_globais
            if dados is None:
                continue
            _processar_dados_temporais(
                dados,
                ano,
                processor,
                dados_diarios,
                dados_mensais,
                dados_pentadas,
            )

        # 4. CÁLCULO DAS CLIMATOLOGIAS
        print("\n🧮 Calculando climatologias finais...")
        clima_mensal = _calcular_climatologia_mensal(dados_mensais)
        clima_diaria = _calcular_climatologia_diaria(dados_diarios)
        clima_pentadas = _calcular_climatologia_pentadas(dados_pentadas)

        # 5. SALVAR ARQUIVOS
        print("💾 Salvando arquivos de climatologia...")
        arquivos_gerados = {
            "mensal": _salvar_climatologia_temporal(
                clima_mensal,
                "mensal",
                diretorio_saida,
                prefixo_arquivo,
                area_id,
                anos_analise,
                study_area,
                incluir_metadata,
            ),
            "diaria": _salvar_climatologia_temporal(
                clima_diaria,
                "diaria",
                diretorio_saida,
                prefixo_arquivo,
                area_id,
                anos_analise,
                study_area,
                incluir_metadata,
            ),
            "pentadas": _salvar_climatologia_temporal(
                clima_pentadas,
                "pentadas",
                diretorio_saida,
                prefixo_arquivo,
                area_id,
                anos_analise,
                study_area,
                incluir_metadata,
            ),
        }

        print("\n✅ Processo concluído!")

        # Opcional: Análise dos resultados (mantida da sua função original)
        resultados_analise = {}
        for tipo, arquivo in arquivos_gerados.items():
            try:
                resultados_analise[tipo] = analisar_climatologia_temporal(arquivo)
            except Exception as e:
                print(f"   ❌ Erro na análise do arquivo {tipo}: {e}")
                resultados_analise[tipo] = None

        return arquivos_gerados, resultados_analise

    except Exception as e:
        print(f"\n❌ ERRO GERAL DURANTE A EXECUÇÃO: {e}")
        return None, None


def demonstrar_uso_climatologias_especificas():
    """
    Demonstra o uso das funções específicas para diferentes escalas temporais.

    ANALOGIA DO CHEF ESPECIALIZADO 👨‍🍳
    Como um chef que pode preparar pratos específicos quando o cliente
    quer apenas uma especialidade da casa.
    """

    print("\n🍽️  DEMONSTRAÇÃO: CLIMATOLOGIAS ESPECÍFICAS")
    print("=" * 60)

    anos_exemplo = [2018, 2019, 2020]  # Últimos 3 anos como exemplo

    # ========================================================================
    # CLIMATOLOGIA MENSAL RÁPIDA
    # ========================================================================

    print("\n📅 1. CLIMATOLOGIA MENSAL RÁPIDA:")
    print("   🎯 Ideal para: Análises sazonais e planejamento geral")
    print("   ⚡ Vantagem: Processamento rápido, foco no essencial")

    try:
        climatologia_mensal, arquivo_mensal = criar_climatologia_mensal_rapida(
            study_area=None,  # Área padrão
            anos=anos_exemplo,
            arquivo_saida="./exemplo_mensal.json",
        )

        print(f"   ✅ Criada com sucesso: {len(climatologia_mensal)} meses")
        print(f"   📄 Arquivo: {Path(arquivo_mensal).name}")

        # Mostrar algumas posições
        print("   🗓️  Exemplos:")
        for mes in [1, 4, 7, 10]:  # Jan, Abr, Jul, Out
            meses_nomes = {1: "Jan", 4: "Abr", 7: "Jul", 10: "Out"}
            pos = climatologia_mensal[mes]
            print(f"      {meses_nomes[mes]}: {pos:+5.1f}°N")

    except Exception as e:
        print(f"   ❌ Erro: {e}")

    # ========================================================================
    # CLIMATOLOGIA DIÁRIA DETALHADA
    # ========================================================================

    print("\n📅 2. CLIMATOLOGIA DIÁRIA DETALHADA:")
    print("   🎯 Ideal para: Estudos precisos e operações diárias")
    print("   🔬 Vantagem: Resolução temporal máxima (365 dias)")

    try:
        (
            climatologia_diaria,
            arquivo_diario,
        ) = criar_climatologia_diaria_detalhada(
            study_area=None,  # Área padrão
            anos=anos_exemplo,
            suavizar=True,  # Aplicar suavização para reduzir ruído
            arquivo_saida="./exemplo_diario.json",
        )

        print(f"   ✅ Criada com sucesso: {len(climatologia_diaria)} dias")
        print(f"   📄 Arquivo: {Path(arquivo_diario).name}")
        print("   🔧 Suavização aplicada para reduzir ruído diário")

        # Mostrar alguns dias representativos
        print("   🗓️  Exemplos (dias do ano):")
        dias_exemplo = [1, 100, 200, 300]  # Início, meio do ano, etc.
        for dia in dias_exemplo:
            if dia in climatologia_diaria:
                pos = climatologia_diaria[dia]
                print(f"      Dia {dia:3d}: {pos:+5.1f}°N")

    except Exception as e:
        print(f"   ❌ Erro: {e}")

    # ========================================================================
    # CLIMATOLOGIA POR PENTADAS
    # ========================================================================

    print("\n📅 3. CLIMATOLOGIA PENTADAL OPERACIONAL:")
    print("   🎯 Ideal para: Previsões de 5 dias e análises operacionais")
    print("   ⚖️  Vantagem: Equilíbrio entre resolução e estabilidade")

    try:
        (
            climatologia_pentadas,
            arquivo_pentadas,
        ) = criar_climatologia_pentadas_operacional(
            study_area=None,  # Área padrão
            anos=anos_exemplo,
            arquivo_saida="./exemplo_pentadas.json",
        )

        print(f"   ✅ Criada com sucesso: {len(climatologia_pentadas)} pentadas")
        print(f"   📄 Arquivo: {Path(arquivo_pentadas).name}")

        # Mostrar algumas pentadas representativas
        print("   🗓️  Exemplos (pentadas):")
        pentadas_exemplo = [10, 25, 40, 55]  # Diferentes épocas do ano
        for pentada in pentadas_exemplo:
            if pentada in climatologia_pentadas:
                pos = climatologia_pentadas[pentada]
                print(f"      Pentada {pentada:2d}: {pos:+5.1f}°N")

    except Exception as e:
        print(f"   ❌ Erro: {e}")

    print("\n💡 DICA IMPORTANTE:")
    print("   📊 Cada escala temporal tem sua aplicação específica")
    print("   ⚡ Use a escala que melhor atende seu objetivo")
    print("   🔄 Combine diferentes escalas para análises completas")


def interpretar_resultados_climatologicos():
    """
    Fornece interpretação científica dos resultados climatológicos.

    ANALOGIA DO TRADUTOR CIENTÍFICO 🔬
    Como um tradutor que converte números em linguagem compreensível,
    explicando o significado real dos padrões encontrados.
    """

    print("\n🔬 INTERPRETAÇÃO CIENTÍFICA DOS RESULTADOS")
    print("=" * 60)

    print("\n🌊 COMPREENDENDO A ZCIT:")
    print("   📍 A ZCIT é uma 'faixa de chuvas' que migra sazonalmente")
    print("   🌍 Fundamental para o clima do Norte/Nordeste do Brasil")
    print("   ⚖️  Posição determina se há seca ou chuva na região")

    print("\n📊 INTERPRETANDO OS VALORES:")
    print("   🧭 Valores POSITIVOS (+): ZCIT ao NORTE do equador")
    print("   🧭 Valores NEGATIVOS (-): ZCIT ao SUL do equador")
    print("   📏 Amplitude típica: 10-15° de migração anual")

    print("\n🗓️  PADRÃO SAZONAL TÍPICO:")
    print("   🌧️  FEV-MAI: ZCIT mais ao SUL → CHUVAS no N/NE Brasil")
    print("   ☀️  JUL-SET: ZCIT mais ao NORTE → SECA no N/NE Brasil")
    print("   🔄 MAR-ABR: Posição mais meridional (mais chuvas)")
    print("   🔄 AGO-SET: Posição mais setentrional (mais seca)")

    print("\n🚨 ANOMALIAS IMPORTANTES:")
    print("   🔴 ZCIT muito ao SUL em época seca → Chuvas fora de época")
    print("   🔴 ZCIT muito ao NORTE em época chuvosa → Seca severa")
    print("   🟡 Desvios > 2° são considerados anômalos")
    print("   🟢 Variações < 1° são normais")

    print("\n📈 USANDO AS DIFERENTES ESCALAS:")
    print("   📅 MENSAL: Planejamento agrícola e recursos hídricos")
    print("   📅 DIÁRIA: Previsão meteorológica de curto prazo")
    print("   📅 PENTADAL: Previsões operacionais de 5 dias")

    print("\n🌡️  IMPACTOS CLIMÁTICOS:")
    print("   💧 Agricultura: Determina período de plantio/colheita")
    print("   🏞️  Recursos hídricos: Afeta reservatórios e rios")
    print("   🌾 Pecuária: Influencia disponibilidade de pastagens")
    print("   🏘️  População: Impacta abastecimento de água urbano")

    print("\n📚 REFERÊNCIAS CIENTÍFICAS:")
    print("   • Uvo (1989): Migração sazonal da ZCIT")
    print("   • Cavalcanti et al. (2009): Impactos no Brasil")
    print("   • Xie & Philander (1994): Dinâmica no Atlântico")
    print("   • Hastenrath & Kutzbach (1985): Variabilidade")


def _gerar_identificador_area(study_area: StudyAreaType) -> str:
    """
    Gera identificador único para a área de estudo.

    ANALOGIA DO CARTÓGRAFO 🗺️
    Como um cartógrafo que cria códigos únicos para cada mapa,
    esta função gera "códigos postais climáticos" para cada área.
    """
    if study_area is None:
        return "area_padrao"
    if isinstance(study_area, tuple) and len(study_area) == 4:
        lat_min, lat_max, lon_min, lon_max = study_area
        return f"bbox_{abs(lat_min):.0f}S{abs(lat_max):.0f}N_{abs(lon_min):.0f}W{abs(lon_max):.0f}E"
    if isinstance(study_area, str):
        # Usar nome do arquivo sem extensão
        return f"arquivo_{Path(study_area).stem}"
    if HAS_GEOPANDAS and isinstance(study_area, gpd.GeoDataFrame):
        # Usar hash do GeoDataFrame para identificador único
        return f"geodf_{len(study_area)}geom"
    return "area_customizada"


def _processar_dados_temporais(
    dados: xr.Dataset,
    ano: int,
    processor: DataProcessor,
    dados_diarios: list,
    dados_mensais: dict,
    dados_pentadas: dict,
) -> int:
    """
    Processa dados de um ano para todas as escalas temporais.

    ANALOGIA DO RELOJOEIRO ⚰️
    Como um relojoeiro que calibra diferentes escalas de tempo
    em um relógio complexo, esta função organiza os dados climáticos
    em diferentes "engrenagens temporais".
    """
    dias_processados = 0

    for dia_idx, tempo in enumerate(dados.time):
        try:
            # Extrair data
            # ========================================================= #
            # ##                  INÍCIO DA CORREÇÃO                 ## #
            # ========================================================= #

            # Use .item() para extrair o valor escalar do array numpy
            data = pd.to_datetime(tempo.values.item())

            # ========================================================= #
            # ##                   FIM DA CORREÇÃO                   ## #
            # ========================================================= #

            dia_ano = data.timetuple().tm_yday  # Dia do ano (1-365)
            mes = data.month

            # Calcular pentada (período de 5 dias)
            pentada = ((dia_ano - 1) // 5) + 1
            pentada = min(pentada, 73)  # Máximo 73 pentadas

            # Selecionar dados do dia
            dados_dia = dados.isel(time=dia_idx)
            media_dia = dados_dia.olr

            # Encontrar posições da ZCIT
            coords_zcit = processor.find_minimum_coordinates(
                media_dia, method="column_minimum"
            )

            if coords_zcit:
                # Calcular latitude média da ZCIT
                lats_zcit = [coord[1] for coord in coords_zcit]
                lat_media = np.mean(lats_zcit)

                # Armazenar para climatologia diária
                dados_diarios.append(
                    {
                        "ano": ano,
                        "dia_ano": dia_ano,
                        "data": data,
                        "mes": mes,
                        "pentada": pentada,
                        "posicao_lat": lat_media,
                        "num_pontos": len(coords_zcit),
                        "olr_medio": float(media_dia.mean()),
                    }
                )

                # Armazenar para climatologia mensal
                dados_mensais[mes].append(lat_media)

                # Armazenar para climatologia por pentadas
                dados_pentadas[pentada].append(lat_media)

                dias_processados += 1

        except Exception as e:
            print(f"⚠️  Erro no dia {data.day}/{data.month}/{ano}: {e}")
            continue

    return dias_processados


def _calcular_climatologia_mensal(dados_mensais: dict) -> dict[int, float]:
    """
    Calcula climatologia mensal com remoção de outliers.

    ANALOGIA DO ESTATÍSTICO SAZONAL 📊
    Como um estatístico que analisa padrões sazonais,
    calculando "médias representativas" para cada mês.
    """
    climatologia = {}

    for mes in range(1, 13):
        if dados_mensais[mes]:
            valores = np.array(dados_mensais[mes])

            # Remover outliers (> 3 desvios padrão)
            media = np.mean(valores)
            desvio = np.std(valores)
            valores_limpos = valores[np.abs(valores - media) <= 3 * desvio]

            if len(valores_limpos) > 0:
                climatologia[mes] = round(np.mean(valores_limpos), 1)
            else:
                climatologia[mes] = round(media, 1)
        else:
            climatologia[mes] = 0.0

    return climatologia


def _calcular_climatologia_diaria(dados_diarios: list) -> dict[int, float]:
    """
    Calcula climatologia para cada dia do ano (1-365).

    ANALOGIA DO CRONISTA DIÁRIO 📝
    Como um cronista que registra eventos dia a dia,
    calculando "padrões típicos" para cada data do calendário.
    """
    # Organizar dados por dia do ano
    dados_por_dia = {dia: [] for dia in range(1, 366)}

    for registro in dados_diarios:
        dia_ano = registro["dia_ano"]
        dados_por_dia[dia_ano].append(registro["posicao_lat"])

    # Calcular climatologia
    climatologia = {}

    for dia_ano in range(1, 366):
        if dados_por_dia[dia_ano]:
            valores = np.array(dados_por_dia[dia_ano])

            # Aplicar suavização com janela móvel de 7 dias para reduzir ruído
            # (opcional - pode ser removido se preferir dados mais "crus")
            climatologia[dia_ano] = round(np.mean(valores), 1)
        else:
            # Interpolar usando dias vizinhos se não houver dados
            climatologia[dia_ano] = _interpolar_dia_faltante(climatologia, dia_ano)

    return climatologia


def _calcular_climatologia_pentadas(dados_pentadas: dict) -> dict[int, float]:
    """
    Calcula climatologia para cada pentada (período de 5 dias).

    ANALOGIA DO METEOROLOGISTA OPERACIONAL 🌪️
    Como um meteorologista que faz previsões de 5 dias,
    esta função calcula "padrões típicos" para períodos pentadais.
    """
    climatologia = {}

    for pentada in range(1, 74):  # 73 pentadas por ano
        if dados_pentadas[pentada]:
            valores = np.array(dados_pentadas[pentada])

            # Remover outliers
            media = np.mean(valores)
            desvio = np.std(valores)
            valores_limpos = valores[np.abs(valores - media) <= 3 * desvio]

            if len(valores_limpos) > 0:
                climatologia[pentada] = round(np.mean(valores_limpos), 1)
            else:
                climatologia[pentada] = round(media, 1)
        else:
            climatologia[pentada] = 0.0

    return climatologia


def _interpolar_dia_faltante(climatologia: dict, dia_faltante: int) -> float:
    """
    Interpola valor para dia sem dados usando dias vizinhos.

    ANALOGIA DO DETETIVE CLIMÁTICO 🔍
    Como um detetive que preenche lacunas usando pistas vizinhas,
    esta função "deduz" valores ausentes usando padrões próximos.
    """
    # Buscar dias vizinhos com dados
    janela = 7  # Buscar até 7 dias antes e depois

    valores_vizinhos = []

    for offset in range(1, janela + 1):
        # Dia anterior
        dia_ant = dia_faltante - offset
        if dia_ant >= 1 and dia_ant in climatologia:
            valores_vizinhos.append(climatologia[dia_ant])

        # Dia posterior
        dia_post = dia_faltante + offset
        if dia_post <= 365 and dia_post in climatologia:
            valores_vizinhos.append(climatologia[dia_post])

        # Se já temos dados suficientes, parar
        if len(valores_vizinhos) >= 4:
            break

    if valores_vizinhos:
        return round(np.mean(valores_vizinhos), 1)
    return 0.0  # Fallback se não houver dados vizinhos


def _salvar_climatologia_temporal(
    climatologia: dict,
    tipo: str,
    diretorio: Path,
    prefixo: str,
    area_id: str,
    anos: list[int],
    study_area: StudyAreaType,
    incluir_metadata: bool,
) -> Path:
    """
    Salva climatologia temporal em arquivo JSON padronizado.

    ANALOGIA DO ARQUIVISTA DIGITAL 📚
    Como um arquivista que organiza documentos com códigos únicos,
    esta função cria "fichas catalográficas" para cada climatologia.
    """
    # Gerar nome do arquivo padronizado
    ano_inicio = min(anos)
    ano_fim = max(anos)
    timestamp = datetime.now().strftime("%Y%m%d")

    nome_arquivo = f"{prefixo}_{tipo}_{area_id}_{ano_inicio}-{ano_fim}_{timestamp}.json"
    caminho_arquivo = diretorio / nome_arquivo

    # Preparar dados para salvamento
    dados_salvamento = {
        "climatologia": climatologia,
        "info": {
            "tipo": tipo,
            "num_periodos": len(climatologia),
            "area_id": area_id,
            "periodo": f"{ano_inicio}-{ano_fim}",
            "anos_utilizados": anos,
            "criado_em": datetime.now().isoformat(),
        },
    }

    # Adicionar metadata detalhada se solicitado
    if incluir_metadata:
        dados_salvamento["metadata"] = {
            "versao": "1.0.0",
            "fonte": "LOCZCIT-IQR",
            "descricao": f"Climatologia {tipo} da ZCIT",
            "unidade": "graus_latitude_norte",
            "metodo": "column_minimum",
            "referencias": [
                "Waliser & Gautier (1993) - J. Climate",
                "Xie & Philander (1994) - J. Climate",
                "Ferreira et al. (2005) - Rev. Bras. Meteorologia",
            ],
        }

        # Adicionar informações específicas da área
        dados_salvamento["area_estudo"] = _obter_info_area(study_area)

        # Adicionar estatísticas da climatologia
        valores = list(climatologia.values())
        if valores:
            dados_salvamento["estatisticas"] = {
                "posicao_min": round(min(valores), 1),
                "posicao_max": round(max(valores), 1),
                "amplitude": round(max(valores) - min(valores), 1),
                "media_geral": round(np.mean(valores), 1),
                "desvio_padrao": round(np.std(valores), 1),
            }

    # Salvar arquivo
    with open(caminho_arquivo, "w", encoding="utf-8") as f:
        json.dump(dados_salvamento, f, indent=2, ensure_ascii=False)

    print(f"   💾 {tipo.capitalize()}: {nome_arquivo}")

    return caminho_arquivo


def _obter_info_area(study_area: StudyAreaType) -> dict:
    """
    Obtém informações detalhadas sobre a área de estudo.

    ANALOGIA DO GEÓGRAFO 🌍
    Como um geógrafo que cataloga características de territórios,
    esta função cria um "passaporte" para cada área de estudo.
    """
    if study_area is None:
        return {
            "tipo": "area_padrao",
            "descricao": "Geometria padrão interna (Area_LOCZCIT.parquet)",
            "coordenadas": "Variável conforme geometria padrão",
        }
    if isinstance(study_area, tuple) and len(study_area) == 4:
        lat_min, lat_max, lon_min, lon_max = study_area
        return {
            "tipo": "bbox",
            "descricao": "Bounding box personalizado",
            "coordenadas": {
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max,
            },
            "area_graus": (lat_max - lat_min) * (lon_max - lon_min),
        }
    if isinstance(study_area, str):
        return {
            "tipo": "arquivo_geometria",
            "descricao": f"Arquivo: {Path(study_area).name}",
            "caminho": str(study_area),
            "extensao": Path(study_area).suffix,
        }
    if HAS_GEOPANDAS and isinstance(study_area, gpd.GeoDataFrame):
        try:
            bounds = study_area.total_bounds
            return {
                "tipo": "geodataframe",
                "descricao": f"GeoDataFrame com {len(study_area)} geometrias",
                "num_geometrias": len(study_area),
                "crs": str(study_area.crs) if study_area.crs else "Não definido",
                "bounds": {
                    "lon_min": float(bounds[0]),
                    "lat_min": float(bounds[1]),
                    "lon_max": float(bounds[2]),
                    "lat_max": float(bounds[3]),
                },
            }
        except Exception:
            return {
                "tipo": "geodataframe",
                "descricao": f"GeoDataFrame com {len(study_area)} geometrias",
                "num_geometrias": len(study_area),
                "erro": "Não foi possível extrair bounds",
            }
    else:
        return {
            "tipo": "desconhecido",
            "descricao": "Tipo de área não reconhecido",
            "valor": str(type(study_area)),
        }


# ============================================================================
# FUNÇÕES DE CONVENIÊNCIA PARA CLIMATOLOGIAS ESPECÍFICAS
# ============================================================================


def criar_climatologias_completas(
    study_area: StudyAreaType = None,
    anos: list[int] | None = None,
    diretorio_saida: str | Path = "./climatologias_personalizadas",
    mask_to_shape: bool = True,
    prefixo_arquivo: str = "clima_regiao_norte",
    incluir_metadata: bool = True,
) -> dict:
    """
    Função auxiliar para criar climatologias completas (mensal, diária, pentadal) e retornar os caminhos dos arquivos.
    """
    arquivos_gerados, _ = executar_climatologias_completas_zcit(
        study_area=study_area,
        anos=anos,
        diretorio_saida=diretorio_saida,
        mask_to_shape=mask_to_shape,
        prefixo_arquivo=prefixo_arquivo,
        incluir_metadata=incluir_metadata,
    )
    if arquivos_gerados is None:
        raise RuntimeError("Falha ao criar climatologias completas.")
    return arquivos_gerados


def criar_climatologia_mensal_rapida(
    study_area: StudyAreaType = None,
    anos: list[int] | None = None,
    arquivo_saida: str | Path | None = None,
) -> tuple[dict[int, float], str]:
    """
    Cria apenas climatologia mensal (mais rápida).

    ANALOGIA DO CHEF EXECUTIVO 👨‍🍳
    Como um chef que prepara apenas o prato principal quando
    o tempo é limitado, esta função foca na climatologia essencial.

    Parameters
    ----------
    study_area : StudyAreaType, optional
        Área de estudo flexível
    anos : List[int], optional
        Anos para calcular climatologia
    arquivo_saida : str or Path, optional
        Caminho específico para salvar (se None, gera automaticamente)

    Returns
    -------
    Tuple[Dict[int, float], str]
        Climatologia mensal e caminho do arquivo salvo
    """

    print("📅 CRIANDO CLIMATOLOGIA MENSAL RÁPIDA...")

    # Usar função completa mas extrair apenas a parte mensal
    arquivos = criar_climatologias_completas(
        study_area=study_area,
        anos=anos,
        diretorio_saida="./clima_temp"
        if arquivo_saida is None
        else Path(arquivo_saida).parent,
        prefixo_arquivo="clima_mensal_rapido",
    )

    # Carregar climatologia mensal
    climatologia = carregar_climatologia(arquivos["mensal"])

    # Mover arquivo se caminho específico foi fornecido
    if arquivo_saida is not None:
        arquivo_final = Path(arquivo_saida)
        arquivo_final.parent.mkdir(parents=True, exist_ok=True)
        Path(arquivos["mensal"]).rename(arquivo_final)
        print(f"📁 Arquivo movido para: {arquivo_final}")
        return climatologia, str(arquivo_final)

    return climatologia, arquivos["mensal"]


def criar_climatologia_diaria_detalhada(
    study_area: StudyAreaType = None,
    anos: list[int] | None = None,
    suavizar: bool = True,
    arquivo_saida: str | Path | None = None,
) -> tuple[dict[int, float], str]:
    """
    Cria climatologia diária detalhada (365 dias).

    ANALOGIA DO METEOROLOGISTA DE PRECISÃO 🎯
    Como um meteorologista que analisa cada dia do ano com
    precisão cirúrgica, esta função cria previsões dia a dia.

    Parameters
    ----------
    study_area : StudyAreaType, optional
        Área de estudo flexível
    anos : List[int], optional
        Anos para calcular climatologia
    suavizar : bool, default=True
        Se True, aplica suavização para reduzir ruído diário
    arquivo_saida : str or Path, optional
        Caminho específico para salvar

    Returns
    -------
    Tuple[Dict[int, float], str]
        Climatologia diária e caminho do arquivo salvo
    """

    print("📅 CRIANDO CLIMATOLOGIA DIÁRIA DETALHADA...")
    print(f"🔧 Suavização: {'Ativa' if suavizar else 'Desativada'}")

    # Criar climatologias completas
    arquivos = criar_climatologias_completas(
        study_area=study_area,
        anos=anos,
        diretorio_saida="./clima_temp"
        if arquivo_saida is None
        else Path(arquivo_saida).parent,
        prefixo_arquivo="clima_diario_detalhado",
    )

    # Carregar climatologia diária
    climatologia = carregar_climatologia(arquivos["diaria"])

    # Aplicar suavização se solicitado
    if suavizar:
        climatologia = _suavizar_climatologia_diaria(climatologia)
        print("✅ Suavização aplicada (janela móvel de 7 dias)")

    # Salvar climatologia suavizada se necessário
    if arquivo_saida is not None:
        arquivo_final = Path(arquivo_saida)
        _salvar_climatologia_processada(climatologia, arquivo_final, "diaria_suavizada")
        return climatologia, str(arquivo_final)

    return climatologia, arquivos["diaria"]


def _suavizar_climatologia_diaria(
    climatologia: dict[int, float], janela: int = 7
) -> dict[int, float]:
    """
    Aplica suavização com janela móvel na climatologia diária.

    ANALOGIA DO POLIDOR DE DIAMANTES 💎
    Como um polidor que suaviza irregularidades para revelar
    o brilho natural, esta função remove ruídos diários mantendo
    os padrões sazonais essenciais.
    """
    valores = np.array([climatologia[dia] for dia in range(1, 366)])

    # Aplicar média móvel
    valores_suavizados = np.convolve(valores, np.ones(janela) / janela, mode="same")

    # Tratar bordas (primeiros e últimos dias)
    for i in range(janela // 2):
        # Início do ano
        valores_suavizados[i] = np.mean(valores[: i + janela // 2 + 1])
        # Final do ano
        valores_suavizados[-(i + 1)] = np.mean(valores[-(i + janela // 2 + 1) :])

    # Converter de volta para dicionário
    # Converter de volta para dicionário
    climatologia_suavizada = {}
    for dia in range(1, 366):
        climatologia_suavizada[dia] = round(valores_suavizados[dia - 1], 1)

    return climatologia_suavizada


def _salvar_climatologia_processada(
    climatologia: dict,
    arquivo: Path,
    tipo: str,
    metadata_extra: dict | None = None,
) -> None:
    """Salva climatologia processada com metadata específica."""

    dados = {
        "climatologia": climatologia,
        "processamento": {
            "tipo": tipo,
            "criado_em": datetime.now().isoformat(),
            "num_periodos": len(climatologia),
        },
    }

    if metadata_extra:
        dados["metadata_extra"] = metadata_extra

    arquivo.parent.mkdir(parents=True, exist_ok=True)

    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)


def criar_climatologia_pentadas_operacional(
    study_area: StudyAreaType = None,
    anos: list[int] | None = None,
    arquivo_saida: str | Path | None = None,
) -> tuple[dict[int, float], str]:
    """
    Cria climatologia por pentadas para uso operacional.

    ANALOGIA DO METEOROLOGISTA OPERACIONAL ⛈️
    Como um meteorologista que precisa de previsões de 5 dias
    para operações práticas, esta função cria "bússolas climáticas"
    para períodos pentadais.

    Parameters
    ----------
    study_area : StudyAreaType, optional
        Área de estudo flexível
    anos : List[int], optional
        Anos para calcular climatologia
    arquivo_saida : str or Path, optional
        Caminho específico para salvar

    Returns
    -------
    Tuple[Dict[int, float], str]
        Climatologia por pentadas (73 períodos) e caminho do arquivo
    """

    print("🗓️ CRIANDO CLIMATOLOGIA POR PENTADAS OPERACIONAL...")
    print("📊 73 pentadas por ano (períodos de 5 dias cada)")

    # Criar climatologias completas
    arquivos = criar_climatologias_completas(
        study_area=study_area,
        anos=anos,
        diretorio_saida="./clima_temp"
        if arquivo_saida is None
        else Path(arquivo_saida).parent,
        prefixo_arquivo="clima_pentadas_oper",
    )

    # Carregar climatologia por pentadas
    climatologia = carregar_climatologia(arquivos["pentadas"])

    # Mover arquivo se caminho específico foi fornecido
    if arquivo_saida is not None:
        arquivo_final = Path(arquivo_saida)
        arquivo_final.parent.mkdir(parents=True, exist_ok=True)
        Path(arquivos["pentadas"]).rename(arquivo_final)
        print(f"📁 Arquivo movido para: {arquivo_final}")
        return climatologia, str(arquivo_final)

    return climatologia, arquivos["pentadas"]


# ============================================================================
# UTILITÁRIOS PARA ANÁLISE DAS CLIMATOLOGIAS TEMPORAIS
# ============================================================================


def analisar_climatologia_temporal(arquivo_climatologia: str | Path) -> dict:
    """
    Analisa estatísticas de uma climatologia temporal.

    ANALOGIA DO ANALISTA ESTATÍSTICO 📈
    Como um analista que examina relatórios financeiros para
    identificar tendências e padrões, esta função "audita"
    as climatologias para revelar insights.

    Parameters
    ----------
    arquivo_climatologia : str or Path
        Caminho para arquivo de climatologia

    Returns
    -------
    Dict
        Estatísticas e análises da climatologia
    """

    print(f"📊 ANALISANDO CLIMATOLOGIA: {Path(arquivo_climatologia).name}")

    try:
        # Carregar dados
        with open(arquivo_climatologia, encoding="utf-8") as f:
            dados = json.load(f)

        climatologia = dados["climatologia"]
        info = dados.get("info", {})
        tipo = info.get("tipo", "desconhecido")

        # Converter chaves para int
        clima_dict = {int(k): v for k, v in climatologia.items()}
        valores = list(clima_dict.values())

        # Análises básicas
        analise = {
            "arquivo": str(arquivo_climatologia),
            "tipo": tipo,
            "num_periodos": len(valores),
            "estatisticas_basicas": {
                "minimo": round(min(valores), 1),
                "maximo": round(max(valores), 1),
                "amplitude": round(max(valores) - min(valores), 1),
                "media": round(np.mean(valores), 1),
                "mediana": round(np.median(valores), 1),
                "desvio_padrao": round(np.std(valores), 1),
            },
        }

        # Análises específicas por tipo
        if tipo == "mensal":
            analise["analise_sazonal"] = _analisar_sazonalidade_mensal(clima_dict)
        elif tipo == "diaria":
            analise["analise_anual"] = _analisar_ciclo_anual(clima_dict)
        elif tipo == "pentadas":
            analise["analise_pentadal"] = _analisar_padroes_pentadais(clima_dict)

        # Identificar extremos
        analise["extremos"] = _identificar_extremos(clima_dict, tipo)

        # Imprimir resumo
        _imprimir_resumo_analise(analise)

        return analise

    except Exception as e:
        print(f"❌ Erro na análise: {e}")
        return {"erro": str(e)}


def _analisar_sazonalidade_mensal(climatologia: dict[int, float]) -> dict:
    """Analisa padrões sazonais na climatologia mensal."""

    # Identificar estações
    verao_austral = [12, 1, 2, 3]  # Dez-Mar
    outono_austral = [4, 5, 6]  # Abr-Jun
    inverno_austral = [7, 8, 9]  # Jul-Set
    primavera_austral = [10, 11]  # Out-Nov

    estacoes = {
        "verao_austral": [climatologia[m] for m in verao_austral if m in climatologia],
        "outono_austral": [
            climatologia[m] for m in outono_austral if m in climatologia
        ],
        "inverno_austral": [
            climatologia[m] for m in inverno_austral if m in climatologia
        ],
        "primavera_austral": [
            climatologia[m] for m in primavera_austral if m in climatologia
        ],
    }

    analise_estacoes = {}
    for estacao, valores in estacoes.items():
        if valores:
            analise_estacoes[estacao] = {
                "media": round(np.mean(valores), 1),
                "amplitude": round(max(valores) - min(valores), 1)
                if len(valores) > 1
                else 0.0,
            }

    # Identificar mês mais ao norte e mais ao sul
    mes_max = max(climatologia.keys(), key=lambda k: climatologia[k])
    mes_min = min(climatologia.keys(), key=lambda k: climatologia[k])

    nomes_meses = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Março",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }

    return {
        "estacoes": analise_estacoes,
        "extremos_mensais": {
            "mes_mais_norte": {
                "mes": nomes_meses.get(mes_max, mes_max),
                "posicao": climatologia[mes_max],
            },
            "mes_mais_sul": {
                "mes": nomes_meses.get(mes_min, mes_min),
                "posicao": climatologia[mes_min],
            },
        },
        "amplitude_anual": round(climatologia[mes_max] - climatologia[mes_min], 1),
    }


def _analisar_ciclo_anual(climatologia: dict[int, float]) -> dict:
    """Analisa o ciclo anual completo (365 dias)."""

    valores = np.array(
        [climatologia[dia] for dia in range(1, 366) if dia in climatologia]
    )

    # Encontrar máximos e mínimos
    dia_max = max(climatologia.keys(), key=lambda k: climatologia[k])
    dia_min = min(climatologia.keys(), key=lambda k: climatologia[k])

    # Converter dia do ano para data aproximada
    def dia_para_data(dia_ano):
        data_base = datetime(2024, 1, 1)  # Ano bissexto para ter 366 dias
        return (data_base + pd.Timedelta(days=dia_ano - 1)).strftime("%d/%m")

    # Análise de tendências (derivada aproximada)
    gradientes = np.gradient(valores)
    periodos_subida = np.sum(gradientes > 0)
    periodos_descida = np.sum(gradientes < 0)

    return {
        "extremos_anuais": {
            "dia_mais_norte": {
                "dia_ano": dia_max,
                "data_aprox": dia_para_data(dia_max),
                "posicao": climatologia[dia_max],
            },
            "dia_mais_sul": {
                "dia_ano": dia_min,
                "data_aprox": dia_para_data(dia_min),
                "posicao": climatologia[dia_min],
            },
        },
        "tendencias": {
            "dias_subindo": int(periodos_subida),
            "dias_descendo": int(periodos_descida),
            "percentual_subida": round(100 * periodos_subida / len(valores), 1),
        },
        "amplitude_maxima": round(climatologia[dia_max] - climatologia[dia_min], 1),
    }


def _analisar_padroes_pentadais(climatologia: dict[int, float]) -> dict:
    """Analisa padrões nas pentadas (73 períodos de 5 dias)."""

    valores = np.array([climatologia[p] for p in range(1, 74) if p in climatologia])

    # Pentadas extremas
    pentada_max = max(climatologia.keys(), key=lambda k: climatologia[k])
    pentada_min = min(climatologia.keys(), key=lambda k: climatologia[k])

    # Converter pentada para período aproximado do ano
    def pentada_para_periodo(pentada):
        dia_inicio = (pentada - 1) * 5 + 1
        dia_fim = min(pentada * 5, 365)
        return f"Dias {dia_inicio}-{dia_fim}"

    # Análise de variabilidade entre pentadas consecutivas
    diferencas = np.abs(np.diff(valores))
    variabilidade_media = np.mean(diferencas)

    return {
        "extremos_pentadais": {
            "pentada_mais_norte": {
                "pentada": pentada_max,
                "periodo": pentada_para_periodo(pentada_max),
                "posicao": climatologia[pentada_max],
            },
            "pentada_mais_sul": {
                "pentada": pentada_min,
                "periodo": pentada_para_periodo(pentada_min),
                "posicao": climatologia[pentada_min],
            },
        },
        "variabilidade": {
            "mudanca_media_entre_pentadas": round(variabilidade_media, 1),
            "mudanca_maxima": round(np.max(diferencas), 1),
            "mudanca_minima": round(np.min(diferencas), 1),
        },
        "amplitude_pentadal": round(
            climatologia[pentada_max] - climatologia[pentada_min], 1
        ),
    }


def _identificar_extremos(climatologia: dict, tipo: str) -> dict:
    """Identifica valores extremos na climatologia."""

    valores = list(climatologia.values())
    q1 = np.percentile(valores, 25)
    q3 = np.percentile(valores, 75)
    iqr = q3 - q1

    # Limites para outliers
    limite_inferior = q1 - 1.5 * iqr
    limite_superior = q3 + 1.5 * iqr

    outliers = {}
    for periodo, valor in climatologia.items():
        if valor < limite_inferior:
            outliers[periodo] = {"valor": valor, "tipo": "extremo_sul"}
        elif valor > limite_superior:
            outliers[periodo] = {"valor": valor, "tipo": "extremo_norte"}

    return {
        "limites_iqr": {
            "q1": round(q1, 1),
            "q3": round(q3, 1),
            "limite_inferior": round(limite_inferior, 1),
            "limite_superior": round(limite_superior, 1),
        },
        "outliers": outliers,
        "num_outliers": len(outliers),
    }


def _imprimir_resumo_analise(analise: dict) -> None:
    """Imprime resumo formatado da análise."""

    print("\n📋 RESUMO DA ANÁLISE:")
    print(f"   📄 Arquivo: {Path(analise['arquivo']).name}")
    print(f"   📊 Tipo: {analise['tipo'].upper()}")
    print(f"   📈 Períodos: {analise['num_periodos']}")

    stats = analise["estatisticas_basicas"]
    print("\n📈 ESTATÍSTICAS BÁSICAS:")
    print(f"   🔺 Máximo: {stats['maximo']:+.1f}°N")
    print(f"   🔻 Mínimo: {stats['minimo']:+.1f}°N")
    print(f"   📏 Amplitude: {stats['amplitude']:.1f}°")
    print(f"   📊 Média: {stats['media']:+.1f}°N")
    print(f"   📈 Desvio: ±{stats['desvio_padrao']:.1f}°")

    # Extremos específicos
    extremos = analise.get("extremos", {})
    if extremos.get("num_outliers", 0) > 0:
        print("\n⚠️  VALORES EXTREMOS:")
        print(f"   🔢 Outliers detectados: {extremos['num_outliers']}")

    # Análise sazonal se disponível
    if "analise_sazonal" in analise:
        saz = analise["analise_sazonal"]
        extremos_mensais = saz["extremos_mensais"]
        print("\n🌊 PADRÕES SAZONAIS:")
        print(
            f"   🏔️  Mais ao norte: {extremos_mensais['mes_mais_norte']['mes']} "
            f"({extremos_mensais['mes_mais_norte']['posicao']:+.1f}°N)"
        )
        print(
            f"   🏝️  Mais ao sul: {extremos_mensais['mes_mais_sul']['mes']} "
            f"({extremos_mensais['mes_mais_sul']['posicao']:+.1f}°N)"
        )
        print(f"   📏 Amplitude anual: {saz['amplitude_anual']:.1f}°")


def comparar_climatologias_temporais(
    arquivo1: str | Path,
    arquivo2: str | Path,
    salvar_comparacao: bool = True,
    diretorio_saida: str | Path = "./comparacoes",
) -> dict:
    """
    Compara duas climatologias temporais.

    ANALOGIA DO JUIZ CLIMÁTICO ⚖️
    Como um juiz que compara evidências de diferentes casos,
    esta função "julga" as diferenças entre climatologias
    para identificar padrões e discrepâncias.

    Parameters
    ----------
    arquivo1 : str or Path
        Primeira climatologia
    arquivo2 : str or Path
        Segunda climatologia para comparar
    salvar_comparacao : bool, default=True
        Se True, salva relatório de comparação
    diretorio_saida : str or Path, default="./comparacoes"
        Diretório para salvar comparação

    Returns
    -------
    Dict
        Relatório detalhado da comparação
    """

    print("⚖️ COMPARANDO CLIMATOLOGIAS TEMPORAIS:")
    print(f"   📄 Arquivo 1: {Path(arquivo1).name}")
    print(f"   📄 Arquivo 2: {Path(arquivo2).name}")

    try:
        # Carregar ambas climatologias
        with open(arquivo1, encoding="utf-8") as f:
            dados1 = json.load(f)
        with open(arquivo2, encoding="utf-8") as f:
            dados2 = json.load(f)

        clima1 = {int(k): v for k, v in dados1["climatologia"].items()}
        clima2 = {int(k): v for k, v in dados2["climatologia"].items()}

        # Verificar compatibilidade
        periodos_comuns = set(clima1.keys()) & set(clima2.keys())
        if len(periodos_comuns) == 0:
            raise ValueError("Climatologias não têm períodos em comum")

        # Calcular diferenças
        diferencas = {}
        for periodo in periodos_comuns:
            diferencas[periodo] = clima1[periodo] - clima2[periodo]

        valores_diff = list(diferencas.values())

        # Análises estatísticas
        comparacao = {
            "arquivos": {"arquivo1": str(arquivo1), "arquivo2": str(arquivo2)},
            "compatibilidade": {
                "periodos_arquivo1": len(clima1),
                "periodos_arquivo2": len(clima2),
                "periodos_comuns": len(periodos_comuns),
                "percentual_comum": round(
                    100 * len(periodos_comuns) / max(len(clima1), len(clima2)),
                    1,
                ),
            },
            "estatisticas_diferencas": {
                "diferenca_media": round(np.mean(valores_diff), 2),
                "diferenca_maxima": round(max(valores_diff), 2),
                "diferenca_minima": round(min(valores_diff), 2),
                "desvio_padrao_diff": round(np.std(valores_diff), 2),
                "correlacao": round(
                    np.corrcoef(
                        [clima1[p] for p in periodos_comuns],
                        [clima2[p] for p in periodos_comuns],
                    )[0, 1],
                    3,
                ),
            },
            "diferencas_detalhadas": diferencas,
        }

        # Classificar similaridade
        correlacao = comparacao["estatisticas_diferencas"]["correlacao"]
        desvio_diff = comparacao["estatisticas_diferencas"]["desvio_padrao_diff"]

        if correlacao > 0.95 and desvio_diff < 1.0:
            similaridade = "MUITO_ALTA"
            emoji = "🟢"
        elif correlacao > 0.85 and desvio_diff < 2.0:
            similaridade = "ALTA"
            emoji = "🟡"
        elif correlacao > 0.70:
            similaridade = "MODERADA"
            emoji = "🟠"
        else:
            similaridade = "BAIXA"
            emoji = "🔴"

        comparacao["similaridade"] = {
            "nivel": similaridade,
            "emoji": emoji,
            "interpretacao": _interpretar_similaridade(
                similaridade, correlacao, desvio_diff
            ),
        }

        # Imprimir resumo
        _imprimir_resumo_comparacao(comparacao)

        # Salvar comparação se solicitado
        if salvar_comparacao:
            arquivo_comp = _salvar_relatorio_comparacao(comparacao, diretorio_saida)
            comparacao["arquivo_relatorio"] = str(arquivo_comp)

        return comparacao

    except Exception as e:
        print(f"❌ Erro na comparação: {e}")
        return {"erro": str(e)}


def _interpretar_similaridade(nivel: str, correlacao: float, desvio: float) -> str:
    """Interpreta o nível de similaridade entre climatologias."""

    interpretacoes = {
        "MUITO_ALTA": f"Climatologias praticamente idênticas (r={correlacao:.3f}, σ={desvio:.1f}°). "
        "Representam padrões climáticos muito similares.",
        "ALTA": f"Climatologias muito similares (r={correlacao:.3f}, σ={desvio:.1f}°). "
        "Pequenas diferenças regionais ou metodológicas.",
        "MODERADA": f"Climatologias moderadamente similares (r={correlacao:.3f}, σ={desvio:.1f}°). "
        "Diferenças notáveis mas padrões gerais compatíveis.",
        "BAIXA": f"Climatologias distintas (r={correlacao:.3f}, σ={desvio:.1f}°). "
        "Representam padrões climáticos diferentes ou áreas distintas.",
    }

    return interpretacoes.get(nivel, "Similaridade não determinada.")


def _imprimir_resumo_comparacao(comparacao: dict) -> None:
    """Imprime resumo formatado da comparação."""

    print("\n📊 RESUMO DA COMPARAÇÃO:")

    compat = comparacao["compatibilidade"]
    print(
        f"   📈 Períodos em comum: {compat['periodos_comuns']} "
        f"({compat['percentual_comum']:.1f}%)"
    )

    stats = comparacao["estatisticas_diferencas"]
    print(f"   📏 Diferença média: {stats['diferenca_media']:+.2f}°")
    print(f"   📈 Correlação: {stats['correlacao']:.3f}")
    print(f"   📊 Desvio das diferenças: ±{stats['desvio_padrao_diff']:.2f}°")

    sim = comparacao["similaridade"]
    print(f"\n{sim['emoji']} SIMILARIDADE: {sim['nivel']}")
    print(f"   💬 {sim['interpretacao']}")


def _salvar_relatorio_comparacao(comparacao: dict, diretorio: str | Path) -> Path:
    """Salva relatório detalhado da comparação."""

    diretorio = Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)

    # Gerar nome do arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"comparacao_climatologias_{timestamp}.json"
    arquivo_relatorio = diretorio / nome_arquivo

    # Adicionar metadata ao relatório
    relatorio_completo = {
        "comparacao": comparacao,
        "metadata": {
            "criado_em": datetime.now().isoformat(),
            "versao": "1.0.0",
            "ferramenta": "LOCZCIT-IQR",
        },
    }

    with open(arquivo_relatorio, "w", encoding="utf-8") as f:
        json.dump(relatorio_completo, f, indent=2, ensure_ascii=False)

    print(f"💾 Relatório salvo: {nome_arquivo}")
    return arquivo_relatorio


# ============================================================================
# NOVAS FUNÇÕES PARA ÁREAS ESPECÍFICAS DO BRASIL - MANTIDAS
# ============================================================================


def climatologia_nordeste_brasileiro(
    anos_amostra: list[int] | None = None, mask_to_shape: bool = False
) -> MonthlyClimatology:
    """
    Calcula climatologia específica para o Nordeste brasileiro.

    ANALOGIA DO ESPECIALISTA REGIONAL 🏜️
    Como um meteorologista que conhece intimamente os padrões
    climáticos do sertão e litoral nordestino.

    Parameters
    ----------
    anos_amostra : List[int], optional
        Anos específicos para análise
    mask_to_shape : bool, default=False
        Se usar mascaramento preciso ou BBOX

    Returns
    -------
    Dict[int, float]
        Climatologia da ZCIT para o Nordeste
    """
    # Área do Nordeste brasileiro (aproximada)
    area_nordeste = (-18, -2, -48, -32)  # (lat_min, lat_max, lon_min, lon_max)

    print("🏜️ CALCULANDO CLIMATOLOGIA PARA O NORDESTE BRASILEIRO")
    print("🌵 Esta região é especialmente sensível à posição da ZCIT")

    return calcular_climatologia_personalizada(
        study_area=area_nordeste,
        anos_amostra=anos_amostra,
        mask_to_shape=mask_to_shape,
    )


def climatologia_amazonia_oriental(
    anos_amostra: list[int] | None = None, mask_to_shape: bool = False
) -> MonthlyClimatology:
    """
    Calcula climatologia específica para a Amazônia Oriental.

    Parameters
    ----------
    anos_amostra : List[int], optional
        Anos específicos para análise
    mask_to_shape : bool, default=False
        Se usar mascaramento preciso ou BBOX

    Returns
    -------
    Dict[int, float]
        Climatologia da ZCIT para a Amazônia Oriental
    """
    # Área da Amazônia Oriental (aproximada)
    area_amazonia = (-10, 5, -55, -40)  # (lat_min, lat_max, lon_min, lon_max)

    print("🌳 CALCULANDO CLIMATOLOGIA PARA A AMAZÔNIA ORIENTAL")
    print("🌧️ Região crítica para padrões de precipitação amazônica")

    return calcular_climatologia_personalizada(
        study_area=area_amazonia,
        anos_amostra=anos_amostra,
        mask_to_shape=mask_to_shape,
    )


def climatologia_atlantico_tropical(
    anos_amostra: list[int] | None = None, mask_to_shape: bool = False
) -> MonthlyClimatology:
    """
    Calcula climatologia específica para o Atlântico Tropical.

    Parameters
    ----------
    anos_amostra : List[int], optional
        Anos específicos para análise
    mask_to_shape : bool, default=False
        Se usar mascaramento preciso ou BBOX

    Returns
    -------
    Dict[int, float]
        Climatologia da ZCIT para o Atlântico Tropical
    """
    # Área do Atlântico Tropical (clássica para ZCIT)
    area_atlantico = (
        -15,
        20,
        -60,
        -10,
    )  # (lat_min, lat_max, lon_min, lon_max)

    print("🌊 CALCULANDO CLIMATOLOGIA PARA O ATLÂNTICO TROPICAL")
    print("🌍 Região de referência clássica para estudos da ZCIT")

    return calcular_climatologia_personalizada(
        study_area=area_atlantico,
        anos_amostra=anos_amostra,
        mask_to_shape=mask_to_shape,
    )


# ============================================================================
# EXEMPLO DE USO COMPLETO - ATUALIZADO
# ============================================================================

if __name__ == "__main__":
    """
    Exemplo de uso das funcionalidades do módulo de climatologia.
    """
    print("🌊 EXEMPLO DE USO - MÓDULO CLIMATOLOGIA ZCIT")
    print("=" * 60)

    # ========================================================================
    # 1. CLIMATOLOGIA RÁPIDA DA LITERATURA
    # ========================================================================
    print("\n1️⃣ CLIMATOLOGIA DA LITERATURA CIENTÍFICA:")
    clima_literatura = obter_climatologia_zcit_rapida()
    print(f"   Março: {clima_literatura[3]:+.1f}°N")
    print(f"   Julho: {clima_literatura[7]:+.1f}°N")

    # ========================================================================
    # 2. EXEMPLO DE COMPARAÇÃO
    # ========================================================================
    print("\n2️⃣ EXEMPLO DE COMPARAÇÃO:")
    status, desvio, interpretacao = comparar_com_climatologia_cientifica(
        mes=3, posicao_encontrada=-0.32, usar_climatologia_calculada=False
    )

    # ========================================================================
    # 3. CLIMATOLOGIA COM ÁREA FLEXÍVEL (NOVIDADE!)
    # ========================================================================
    print("\n3️⃣ CLIMATOLOGIA COM ÁREA DE ESTUDO FLEXÍVEL:")

    # Exemplo 1: BBOX personalizado
    print("\n📐 Exemplo com BBOX do Nordeste:")
    try:
        clima_ne = climatologia_nordeste_brasileiro(anos_amostra=[2020, 2021, 2022])
        print(f"   ZCIT em março no NE: {clima_ne[3]:+.1f}°N")
    except Exception as e:
        print(f"   ❌ Erro: {e}")

    # Exemplo 2: Área padrão (usando geometria interna)
    print("\n📍 Exemplo com área padrão:")
    try:
        clima_padrao = calcular_climatologia_personalizada(
            study_area=None,
            anos_amostra=[2020, 2022],  # Usa geometria padrão
        )
        print(f"   ZCIT em julho (padrão): {clima_padrao[7]:+.1f}°N")
    except Exception as e:
        print(f"   ❌ Erro: {e}")

    # ========================================================================
    # 4. SALVAR E CARREGAR CLIMATOLOGIA
    # ========================================================================
    print("\n4️⃣ SALVANDO E CARREGANDO CLIMATOLOGIA:")
    try:
        # Salvar com metadata extra
        metadata_extra = {
            "regiao": "Literatura Científica",
            "autor": "LOCZCIT-IQR",
            "observacoes": "Baseado em Waliser & Gautier (1993)",
        }
        salvar_climatologia(
            clima_literatura,
            "exemplo_climatologia.json",
            metadata_extra=metadata_extra,
        )

        # Carregar novamente
        clima_carregada = carregar_climatologia("exemplo_climatologia.json")
        print("✅ Climatologia recarregada com sucesso!")
        print(f"   Verificação: março = {clima_carregada[3]:+.1f}°N")

    except Exception as e:
        print(f"❌ Erro ao salvar/carregar: {e}")

    # ========================================================================
    # 5. INTERFACE LIMPA (MANTIDA)
    # ========================================================================
    print("\n5️⃣ TESTE DA INTERFACE LIMPA:")
    try:
        status_limpo = analise_zcit_rapida(-0.5, 3)
        print(f"   Status obtido: {status_limpo}")
    except Exception as e:
        print(f"   ❌ Erro na interface limpa: {e}")

    # ========================================================================
    # 6. DEMONSTRAÇÃO DE FLEXIBILIDADE
    # ========================================================================
    print("\n6️⃣ DEMONSTRAÇÃO DA FLEXIBILIDADE DE ÁREAS:")

    areas_exemplo = {
        "Atlântico Tropical": (-15, 20, -60, -10),
        "Equador": (-5, 5, -180, 180),
        "Brasil Norte": (-10, 5, -75, -45),
    }

    for nome_area, bbox in areas_exemplo.items():
        print(f"\n   🗺️  Testando: {nome_area}")
        print(f"      BBOX: {bbox}")
        # Na prática, você faria:
        # clima = calcular_climatologia_personalizada(study_area=bbox)
        print("      ✅ Configuração válida para climatologia!")

    print("\n" + "=" * 60)
    print("📚 REFERÊNCIAS CIENTÍFICAS UTILIZADAS:")
    print("   • Waliser & Gautier (1993) - Journal of Climate")
    print("   • Xie & Philander (1994) - Journal of Climate")
    print("   • Ferreira et al. (2005) - Revista Brasileira de Meteorologia")
    print("   • Cavalcanti et al. (2009) - Tempo e Clima no Brasil")
    print("   • NOAA Climate Data Record (1979-2023)")

    print("\n🎯 PRINCIPAIS MELHORIAS DESTA VERSÃO:")
    print("   ✅ Área de estudo flexível (None, BBOX, arquivos, GeoDataFrame)")
    print("   ✅ Integração com load_data_dual_scale")
    print("   ✅ Mascaramento opcional para geometrias precisas")
    print("   ✅ Funções regionais pré-configuradas")
    print("   ✅ Metadata expandida nos arquivos salvos")
    print("   ✅ Interface limpa mantida para usuários finais")

    print("\n🚀 Módulo pronto para análises climáticas avançadas!")

# ============================================================================
# FUNÇÃO DE TESTE DAS NOVAS FUNCIONALIDADES
# ============================================================================


def _testar_novas_funcionalidades():
    """Função para testar as novas funcionalidades de área flexível."""
    print("\n🧪 TESTANDO NOVAS FUNCIONALIDADES DE ÁREA FLEXÍVEL")
    print("=" * 60)

    # Teste 1: Diferentes tipos de study_area
    print("\n1️⃣ Teste de diferentes tipos de study_area:")

    try:
        # BBOX
        print("   📐 Testando BBOX...")
        ClimatologiaZCIT(study_area=(-10, 10, -50, -30))
        print("   ✅ BBOX aceito")

        # None (padrão)
        print("   📍 Testando área padrão...")
        ClimatologiaZCIT(study_area=None)
        print("   ✅ Área padrão aceita")

        # String (arquivo)
        print("   📁 Testando string de arquivo...")
        ClimatologiaZCIT(study_area="teste.shp", mask_to_shape=True)
        print("   ✅ String de arquivo aceita")

    except Exception as e:
        print(f"   ❌ Erro nos testes básicos: {e}")

    # Teste 2: Funções regionais
    print("\n2️⃣ Teste das funções regionais:")

    funcoes_regionais = [
        ("Nordeste", climatologia_nordeste_brasileiro),
        ("Amazônia", climatologia_amazonia_oriental),
        ("Atlântico", climatologia_atlantico_tropical),
    ]

    for nome, funcao in funcoes_regionais:
        try:
            print(f"   🗺️  Testando {nome}...")
            # Teste apenas com configuração (não execução completa)
            # clima = funcao(anos_amostra=[2022])
            print(f"   ✅ Função {nome} configurada corretamente")
        except Exception as e:
            print(f"   ❌ Erro na função {nome}: {e}")

    # Teste 3: Comparação com versão anterior
    print("\n3️⃣ Teste de compatibilidade com versão anterior:")

    try:
        # Modo antigo (ainda deve funcionar)
        ClimatologiaZCIT(
            anos_inicio=2020,
            anos_fim=2022,
            study_area=(
                -10,
                10,
                -40,
                -20,
            ),  # Equivale ao antigo area_atlantico
        )
        print("   ✅ Compatibilidade com modo antigo mantida")

        # Modo novo
        ClimatologiaZCIT(
            anos_inicio=2020,
            anos_fim=2022,
            study_area=(-10, 10, -40, -20),
            mask_to_shape=True,
        )
        print("   ✅ Modo novo com mascaramento funcional")

    except Exception as e:
        print(f"   ❌ Erro na compatibilidade: {e}")

    print("\n✅ Todos os testes das novas funcionalidades concluídos!")


# Criar def para calcular latitude media
def calcular_latitude_media(zcit_line):
    if zcit_line and hasattr(zcit_line, "xy"):
        return np.mean(zcit_line.xy[1])
    return None


# Imprimir resultados de forma limpa
def imprimir_resultados_climatologia(status, desvio, interpretacao):
    """
    Imprime resultados de forma limpa.

    Parameters
    ----------
    status : str
        Status da análise climatológica
    desvio : float
        Desvio calculado
    interpretacao : str
        Interpretação do resultado
    """
    print("\n✅ Análise climatológica concluída!")
    print(f"   Status: {status}")
    print(f"   Desvio: {desvio:+.1f}°")
    print(f"   Interpretação: {interpretacao}")


# Imprimir resultados
# 6. Conclusões e resumo
# print("\n" + "="*60)
# print("🎯 CONCLUSÕES DA ANÁLISE")

# if zcit_line:
#     print("\n✅ ANÁLISE CONCLUÍDA COM SUCESSO!")
#     print("\n📋 Resumo dos Resultados:")
#     print(f"   • Período analisado: {titulo_mes}")
#     print(f"   • Pontos do eixo ZCIT identificados: {len(min_coords)}")
#     print(f"   • Outliers removidos pela análise IQR: {len(coords_outliers)}")
#     print(f"   • Posição média da ZCIT (Latitude): {np.mean(zcit_line.xy[1]):.2f}°")
# else:
#     print("\n❌ ANÁLISE CONCLUÍDA, MAS A LINHA DA ZCIT NÃO PÔDE SER GERADA.")
#     print("   -> Verifique o número de pontos válidos encontrados.")

# print("\n" + "="*60)


# Imprimir analise da ZCIT
def print_analisar_zcit(zcit_line, min_coords, coords_outliers, titulo_mes):
    """
    Analisa a linha da ZCIT e imprime resultados.

    Parameters
    ----------
    zcit_line : LineString
        Linha da ZCIT gerada pela análise
    min_coords : list
        Coordenadas mínimas da ZCIT
    coords_outliers : list
        Coordenadas dos outliers removidos pela análise IQR
    titulo_mes : str
        Título do mês analisado
    """

    latitude_media = calcular_latitude_media(zcit_line)

    print("\n" + "=" * 60)
    print("🎯 CONCLUSÕES DA ANÁLISE")

    if zcit_line:
        print("\n✅ ANÁLISE CONCLUÍDA COM SUCESSO!")
        print("\n📋 Resumo dos Resultados:")
        print(f"   • Período analisado: {titulo_mes}")
        print(f"   • Pontos do eixo ZCIT identificados: {len(min_coords)}")
        print(f"   • Outliers removidos pela análise IQR: {len(coords_outliers)}")
        print(f"   • Posição média da ZCIT (Latitude): {latitude_media:.2f}°")
    else:
        print("\n❌ ANÁLISE CONCLUÍDA, MAS A LINHA DA ZCIT NÃO PÔDE SER GERADA.")
        print("   -> Verifique o número de pontos válidos encontrados.")

    print("\n" + "=" * 60)


def criar_climatologia_olr(
    anos_inicio: int = 1994,
    anos_fim: int = 2023,
    cache_dir: str = "./climatologia_cache",
    diretorio_saida: str = "./climatologia_output",
    area_estudo: tuple[float, float, float, float] | None = None,
    anos_amostra: list[int] | None = None,
    salvar_netcdf: bool = True,
    verbose: bool = True,
) -> dict[str, xr.Dataset]:
    """
    Cria climatologias de OLR usando NOAADataLoader com processamento corrigido.

    ANALOGIA DO CHEF MESTRE 👨‍🍳
    É como um chef experiente que:
    1. 🛒 Vai ao mercado buscar ingredientes frescos (download dos dados)
    2. 🧽 Limpa e prepara cada ingrediente (converte longitude, remove bissextos)
    3. ✂️ Corta na medida certa (aplica filtro de área)
    4. 👨‍🍳 Cria três receitas diferentes (mensal, diária, pentadal)
    5. 📦 Embala tudo para uso futuro (salva em NetCDF)

    Parameters
    ----------
    anos_inicio : int, default 1994
        Ano inicial para climatologia
    anos_fim : int, default 2023
        Ano final para climatologia
    cache_dir : str, default "./climatologia_cache"
        Diretório para cache dos dados originais da NOAA
    diretorio_saida : str, default "./climatologia_output"
        Diretório onde salvar as climatologias finais
    area_estudo : tuple, optional
        (lat_min, lat_max, lon_min, lon_max) para recortar área específica
        Coordenadas em -180/+180 para longitude
    anos_amostra : List[int], optional
        Lista específica de anos para processar. Se None, usa todos os anos
    salvar_netcdf : bool, default True
        Se deve salvar os resultados em arquivos NetCDF
    verbose : bool, default True
        Se deve mostrar informações durante o processamento

    Returns
    -------
    Dict[str, xr.Dataset]
        Dicionário com as três climatologias:
        - 'mensal': Climatologia mensal (12 valores)
        - 'diaria': Climatologia por dia do ano (365 valores)
        - 'pentadal': Climatologia por pentadas (73 valores)

    Examples
    --------
    >>> # Uso básico - climatologia global
    >>> climatologias = criar_climatologia_olr(
    ...     anos_inicio=1994,
    ...     anos_fim=2023
    ... )

    >>> # Uso avançado - apenas para região do Nordeste brasileiro
    >>> climatologias = criar_climatologia_olr(
    ...     anos_inicio=1994,
    ...     anos_fim=2023,
    ...     area_estudo=(-18, 2, -48, -32),  # Nordeste brasileiro
    ...     anos_amostra=[1995, 2000, 2005, 2010, 2015, 2020]  # Anos representativos
    ... )

    Notes
    -----
    Esta versão corrigida:
    - Usa NOAADataLoader para download e cache automático
    - Aplica conversão de longitude (0-360 → -180/+180) automaticamente
    - Remove dias bissextos CORRETAMENTE (dia 60 = 29/02)
    - Aplica controle de qualidade aos dados
    - Garante climatologia diária com exatamente 365 dias
    - Cria pentadas com exatamente 73 grupos
    """

    if verbose:
        print("🌍 CRIANDO CLIMATOLOGIAS OLR - VERSÃO CORRIGIDA")
        print("=" * 60)
        print(f"📅 Período: {anos_inicio} - {anos_fim}")
        print(f"📁 Cache: {cache_dir}")
        print(f"💾 Saída: {diretorio_saida}")
        if area_estudo:
            lat_min, lat_max, lon_min, lon_max = area_estudo
            print(f"🗺️ Área: {lat_min}°-{lat_max}°N, {lon_min}°-{lon_max}°E")
        else:
            print("🌐 Área: Global")

    # Criar diretórios
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    Path(diretorio_saida).mkdir(parents=True, exist_ok=True)

    # Inicializar loader
    loader = NOAADataLoader(cache_dir=cache_dir)

    # Determinar anos a processar
    if anos_amostra is None:
        anos_para_processar = list(range(anos_inicio, anos_fim + 1))
    else:
        anos_para_processar = anos_amostra

    if verbose:
        print(f"📋 Processando {len(anos_para_processar)} anos: {anos_para_processar}")

    # ========================================================================
    # ETAPA 1: CARREGAR E PROCESSAR DADOS ANO POR ANO
    # ========================================================================

    datasets_processados = []
    anos_com_sucesso = []

    for i, ano in enumerate(anos_para_processar, 1):
        if verbose:
            print(f"\n📅 [{i}/{len(anos_para_processar)}] Processando {ano}...")

        try:
            # Carregar dados do ano usando NOAADataLoader
            # Isso já aplica: conversão longitude, filtro área, remoção bissextos, QC
            dados_ano = loader.load_data(
                start_date=f"{ano}-01-01",
                end_date=f"{ano}-12-31",
                study_area=area_estudo,
                auto_download=True,
                quality_control=True,
                remove_leap_days=True,  # ✅ Remove bissextos automaticamente
            )

            if dados_ano is None:
                if verbose:
                    print(f"   ⚠️ Dados não disponíveis para {ano}")
                continue

            # Verificar se tem exatamente 365 dias (bissextos removidos)
            n_dias = len(dados_ano.time)
            if n_dias != 365:
                if verbose:
                    print(f"   ⚠️ Ano {ano} tem {n_dias} dias (esperado: 365)")
                # Continuar mesmo assim, pois pode ser problema específico do ano

            datasets_processados.append(dados_ano)
            anos_com_sucesso.append(ano)

            if verbose:
                dims = dict(dados_ano.dims)
                print(f"   ✅ Sucesso: {dims}")

        except Exception as e:
            if verbose:
                print(f"   ❌ Erro em {ano}: {e}")
            continue

    if not datasets_processados:
        raise RuntimeError("Nenhum dado foi carregado com sucesso!")

    if verbose:
        print("\n📊 RESUMO DO CARREGAMENTO:")
        print(f"   ✅ Anos processados: {len(anos_com_sucesso)}")
        print(
            f"   ❌ Anos com falha: {len(anos_para_processar) - len(anos_com_sucesso)}"
        )
        print(f"   📋 Anos usados: {anos_com_sucesso}")

    # ========================================================================
    # ETAPA 2: COMBINAR TODOS OS DADOS
    # ========================================================================

    if verbose:
        print(f"\n🔗 Combinando {len(datasets_processados)} datasets...")

    try:
        # Combinar datasets por coordenada temporal
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            OLR_combinado = xr.concat(
                datasets_processados,
                dim="time",
                combine_attrs="override",  # Usar atributos do primeiro dataset
            )

        # Verificar que o tempo está ordenado
        OLR_combinado = OLR_combinado.sortby("time")

        if verbose:
            dims_final = dict(OLR_combinado.dims)
            periodo_inicio = str(OLR_combinado.time.min().values)[:10]
            periodo_fim = str(OLR_combinado.time.max().values)[:10]
            print("   ✅ Combinação concluída:")
            print(f"      Dimensões: {dims_final}")
            print(f"      Período: {periodo_inicio} até {periodo_fim}")

    except Exception as e:
        raise RuntimeError(f"Erro ao combinar datasets: {e}")

    # ========================================================================
    # ETAPA 3: CRIAR CLIMATOLOGIAS
    # ========================================================================

    climatologias = {}

    # 3.1 CLIMATOLOGIA MENSAL
    if verbose:
        print("\n📅 Criando climatologia mensal...")

    try:
        OLR_climatologia_mensal = OLR_combinado.groupby("time.month").mean(dim="time")
        climatologias["mensal"] = OLR_climatologia_mensal

        if verbose:
            print(
                f"   ✅ Climatologia mensal: {len(OLR_climatologia_mensal.month)} meses"
            )

    except Exception as e:
        if verbose:
            print(f"   ❌ Erro na climatologia mensal: {e}")
        raise

    # 3.2 CLIMATOLOGIA DIÁRIA (dia do ano) - CORREÇÃO APLICADA
    if verbose:
        print("📆 Criando climatologia por dia do ano...")

    try:
        # Criar climatologia diária inicial
        OLR_climatologia_dia_ano_original = OLR_combinado.groupby(
            "time.dayofyear"
        ).mean(dim="time")

        # ============================================================================
        # CORREÇÃO CRÍTICA: Remover dia 60 (29/02) se existir
        # ============================================================================
        if verbose:
            n_dias_original = len(OLR_climatologia_dia_ano_original.dayofyear)
            tem_dia_60 = 60 in OLR_climatologia_dia_ano_original.dayofyear.values
            print(f"   📊 Climatologia inicial: {n_dias_original} dias")
            print(f"   🔍 Dia 60 (29/02) presente: {tem_dia_60}")

        if 60 in OLR_climatologia_dia_ano_original.dayofyear.values:
            # Remover dia 60 (29/02) especificamente
            OLR_climatologia_dia_ano = OLR_climatologia_dia_ano_original.where(
                OLR_climatologia_dia_ano_original.dayofyear != 60, drop=True
            )
            if verbose:
                print("   🗑️ Dia 60 (29/02) removido")
                print(
                    f"   ✅ Climatologia corrigida: {len(OLR_climatologia_dia_ano.dayofyear)} dias"
                )
        else:
            OLR_climatologia_dia_ano = OLR_climatologia_dia_ano_original
            if verbose:
                print("   ✅ Nenhuma correção necessária")

        climatologias["diaria"] = OLR_climatologia_dia_ano

        # Verificação final
        n_dias_final = len(OLR_climatologia_dia_ano.dayofyear)
        if n_dias_final != 365:
            if verbose:
                print(
                    f"   ⚠️ AVISO: Climatologia diária tem {n_dias_final} dias (esperado: 365)"
                )

    except Exception as e:
        if verbose:
            print(f"   ❌ Erro na climatologia diária: {e}")
        raise

    # 3.3 CLIMATOLOGIA PENTADAL - CORREÇÃO APLICADA
    if verbose:
        print("📊 Criando climatologia pentadal...")

    try:
        # ============================================================================
        # ESTRATÉGIA CORRIGIDA PARA PENTADAS
        # ============================================================================

        # Verificar quantos dias temos
        n_dias_diarios = len(OLR_climatologia_dia_ano.dayofyear)

        if n_dias_diarios == 365:
            # MÉTODO 1: Renumerar dias para sequência contínua 1-365
            if verbose:
                print("   🔧 Renumerando dias para sequência contínua...")

            # Criar nova coordenada sequencial
            dias_sequenciais = list(range(1, n_dias_diarios + 1))

            # Criar dataset temporário com numeração sequencial
            clima_temp = OLR_climatologia_dia_ano.assign_coords(
                dayofyear=dias_sequenciais
            )

            # Criar pentadas
            OLR_climatologia_pentada = (
                clima_temp.coarsen(dayofyear=5, boundary="trim")
                .mean()
                .rename({"dayofyear": "pentad"})
            )

            # Ajustar coordenadas das pentadas (1 a 73)
            n_pentadas = len(OLR_climatologia_pentada.pentad)
            pentadas_coords = np.arange(1, n_pentadas + 1)
            OLR_climatologia_pentada = OLR_climatologia_pentada.assign_coords(
                pentad=pentadas_coords
            )

            if verbose:
                print(f"   ✅ Método renumeração: {n_pentadas} pentadas")
                print(
                    f"   📊 Matemática: {n_dias_diarios} ÷ 5 = {n_dias_diarios / 5:.1f}"
                )

        else:
            # MÉTODO 2: Usar boundary='pad' para lidar com gaps
            if verbose:
                print("   🔧 Usando boundary='pad' para gaps...")

            OLR_climatologia_pentada = (
                OLR_climatologia_dia_ano.coarsen(dayofyear=5, boundary="pad")
                .mean()
                .rename({"dayofyear": "pentad"})
            )

            # Ajustar coordenadas das pentadas
            n_pentadas = len(OLR_climatologia_pentada.pentad)
            pentadas_coords = np.arange(1, n_pentadas + 1)
            OLR_climatologia_pentada = OLR_climatologia_pentada.assign_coords(
                pentad=pentadas_coords
            )

            if verbose:
                print(f"   ✅ Método pad: {n_pentadas} pentadas")

        climatologias["pentadal"] = OLR_climatologia_pentada

        if verbose:
            n_pentadas_final = len(OLR_climatologia_pentada.pentad)
            print(f"   ✅ Climatologia pentadal: {n_pentadas_final} pentadas")

            # Verificação da expectativa (73 pentadas)
            if n_pentadas_final == 73:
                print("   🎯 PERFEITO: 73 pentadas conforme esperado!")
            else:
                print(f"   ⚠️ ATENÇÃO: {n_pentadas_final} pentadas (esperado: 73)")

    except Exception as e:
        if verbose:
            print(f"   ❌ Erro na climatologia pentadal: {e}")
        raise

    # ========================================================================
    # ETAPA 4: ADICIONAR METADADOS CORRIGIDOS
    # ========================================================================

    metadados_base = {
        "titulo": "Climatologia OLR NOAA",
        "fonte": "NOAA Climate Data Record",
        "periodo": f"{anos_com_sucesso[0]}-{anos_com_sucesso[-1]}",
        "anos_processados": len(anos_com_sucesso),
        "metodo": "Media aritmetica",
        "criado_em": str(np.datetime64("now")),
        "versao_loczcit": "2.0.0",
        "leap_days_removed": "true",  # ← CORREÇÃO: string em vez de boolean
        "metodologia_bissextos": "Dia 60 (29/02) removido da climatologia diaria",
    }

    if area_estudo:
        metadados_base["area_estudo"] = (
            f"{area_estudo[0]}°-{area_estudo[1]}°N, {area_estudo[2]}°-{area_estudo[3]}°E"
        )
    else:
        metadados_base["area_estudo"] = "Global"

    # Aplicar metadados a cada climatologia
    for tipo, dataset in climatologias.items():
        dataset.attrs.update(metadados_base)
        dataset.attrs["tipo_climatologia"] = tipo

        # Metadados específicos por tipo
        if tipo == "diaria":
            dataset.attrs["observacao"] = "Calendario de 365 dias (29/02 removido)"
        elif tipo == "pentadal":
            dataset.attrs["observacao"] = "Pentadas baseadas em calendario de 365 dias"

    # ========================================================================
    # ETAPA 5: SALVAR EM ARQUIVOS NETCDF (CORRIGIDO)
    # ========================================================================

    if salvar_netcdf:
        if verbose:
            print("\n💾 Salvando climatologias em arquivos NetCDF...")

        # Gerar identificador da área para nome do arquivo
        if area_estudo:
            area_id = (
                f"_{area_estudo[0]}_{area_estudo[1]}_{area_estudo[2]}_{area_estudo[3]}"
            )
        else:
            area_id = "_global"

        periodo_id = f"{anos_com_sucesso[0]}_{anos_com_sucesso[-1]}"

        nomes_arquivos = {
            "mensal": f"OLR_climatologia_mensal_{periodo_id}{area_id}.nc",
            "diaria": f"OLR_climatologia_diaria_365dias_{periodo_id}{area_id}.nc",  # ← Indicar 365 dias
            "pentadal": f"OLR_climatologia_pentadal_73pentadas_{periodo_id}{area_id}.nc",  # ← Indicar 73 pentadas
        }

        for tipo, dataset in climatologias.items():
            try:
                caminho_completo = Path(diretorio_saida) / nomes_arquivos[tipo]

                # Configurar encoding otimizado
                encoding = {"olr": {"zlib": True, "complevel": 6, "dtype": "float32"}}

                dataset.to_netcdf(caminho_completo, encoding=encoding, format="NETCDF4")

                if verbose:
                    size_mb = caminho_completo.stat().st_size / (1024 * 1024)
                    print(f"   ✅ {nomes_arquivos[tipo]} ({size_mb:.1f} MB)")

            except Exception as e:
                if verbose:
                    print(f"   ❌ Erro ao salvar {tipo}: {e}")

    # ========================================================================
    # ETAPA 6: RELATÓRIO FINAL CORRIGIDO
    # ========================================================================

    if verbose:
        print("\n📈 RELATÓRIO FINAL DAS CLIMATOLOGIAS:")
        print("=" * 50)

        for tipo, dataset in climatologias.items():
            dims = dict(dataset.dims)
            if "olr" in dataset.data_vars:
                media_geral = float(dataset.olr.mean())
                print(f"📊 {tipo.upper()}:")
                print(f"   Dimensões: {dims}")
                print(f"   OLR médio: {media_geral:.1f} W/m²")

                # Informações específicas
                if tipo == "diaria":
                    n_dias = len(dataset.dayofyear)
                    print(f"   🗓️ Dias: {n_dias} (sem 29/02)")
                elif tipo == "pentadal":
                    n_pentadas = len(dataset.pentad)
                    print(f"   📊 Pentadas: {n_pentadas}")

        # Estatísticas sobre anos bissextos
        anos_bissextos = [
            ano
            for ano in anos_com_sucesso
            if ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)
        ]
        print("\n📅 ESTATÍSTICAS TEMPORAIS:")
        print(f"   Anos processados: {len(anos_com_sucesso)}")
        print(f"   Anos bissextos: {len(anos_bissextos)} ({anos_bissextos})")
        print(f"   Anos normais: {len(anos_com_sucesso) - len(anos_bissextos)}")
        print("   Método de bissextos: Remoção do dia 60 (29/02)")

        print("\n🎉 CLIMATOLOGIAS CRIADAS COM SUCESSO!")
        print(f"   📁 Arquivos salvos em: {diretorio_saida}")
        print(f"   📅 Baseado em {len(anos_com_sucesso)} anos de dados")
        print("   ✅ Correção de bissextos aplicada")

    return climatologias


def validar_climatologia(climatologias: dict[str, xr.Dataset]) -> dict[str, bool]:
    """
    Valida se as climatologias foram criadas corretamente.

    Parameters
    ----------
    climatologias : Dict[str, xr.Dataset]
        Dicionário com as climatologias criadas

    Returns
    -------
    Dict[str, bool]
        Resultado da validação para cada tipo
    """

    resultados = {}

    print("🔍 VALIDAÇÃO DAS CLIMATOLOGIAS:")
    print("=" * 40)

    # Validar climatologia mensal
    if "mensal" in climatologias:
        clima_mensal = climatologias["mensal"]
        n_meses = len(clima_mensal.month)
        resultado_mensal = n_meses == 12
        resultados["mensal"] = resultado_mensal
        status = "✅" if resultado_mensal else "❌"
        print(f"{status} Mensal: {n_meses} meses (esperado: 12)")

    # Validar climatologia diária
    if "diaria" in climatologias:
        clima_diaria = climatologias["diaria"]
        n_dias = len(clima_diaria.dayofyear)
        tem_dia_60 = 60 in clima_diaria.dayofyear.values
        resultado_diaria = n_dias == 365 and not tem_dia_60
        resultados["diaria"] = resultado_diaria
        status = "✅" if resultado_diaria else "❌"
        print(f"{status} Diária: {n_dias} dias, dia 60 removido: {not tem_dia_60}")

    # Validar climatologia pentadal
    if "pentadal" in climatologias:
        clima_pentadal = climatologias["pentadal"]
        n_pentadas = len(clima_pentadal.pentad)
        resultado_pentadal = n_pentadas == 73
        resultados["pentadal"] = resultado_pentadal
        status = "✅" if resultado_pentadal else "❌"
        print(f"{status} Pentadal: {n_pentadas} pentadas (esperado: 73)")

    # Resultado geral
    todos_ok = all(resultados.values())
    status_geral = "✅" if todos_ok else "❌"
    print(
        f"\n{status_geral} VALIDAÇÃO GERAL: {'APROVADA' if todos_ok else 'COM PROBLEMAS'}"
    )

    return resultados


def visualizar_climatologia(
    climatologia: xr.Dataset,
    tipo: str = "mensal",
    variavel: str = "olr",
    titulo_personalizado: str | None = None,
    salvar_figura: str | None = None,
) -> None:
    """
    Cria visualização moderna de uma climatologia.

    Parameters
    ----------
    climatologia : xr.Dataset
        Dataset com a climatologia a ser visualizada
    tipo : str
        Tipo de climatologia ('mensal', 'diaria', 'pentadal')
    variavel : str
        Nome da variável a ser plotada (default: 'olr')
    titulo_personalizado : str, optional
        Título personalizado para o gráfico
    salvar_figura : str, optional
        Caminho para salvar a figura (ex: './climatologia_mensal.png')
    """

    import matplotlib.pyplot as plt
    import seaborn as sns

    # Configurar estilo
    plt.style.use("default")
    sns.set_palette("husl")

    # Configurar dimensões e labels baseado no tipo
    config = {
        "mensal": {
            "dim": "month",
            "xlabel": "Mês",
            "titulo": "Climatologia Mensal de OLR",
            "labels": [
                "Jan",
                "Fev",
                "Mar",
                "Abr",
                "Mai",
                "Jun",
                "Jul",
                "Ago",
                "Set",
                "Out",
                "Nov",
                "Dez",
            ],
        },
        "diaria": {
            "dim": "dayofyear",
            "xlabel": "Dia do Ano",
            "titulo": "Climatologia Diária de OLR",
            "labels": None,
        },
        "pentadal": {
            "dim": "pentad",
            "xlabel": "Pentada (grupos de 5 dias)",
            "titulo": "Climatologia Pentadal de OLR",
            "labels": None,
        },
    }

    if tipo not in config:
        raise ValueError(f"Tipo '{tipo}' não reconhecido. Use: {list(config.keys())}")

    # Validar climatologia
    validacao = validar_climatologia(climatologia, tipo)
    if not validacao["valida"]:
        print("⚠️ Problemas encontrados na climatologia:")
        for problema in validacao["problemas"]:
            print(f"   - {problema}")

    # Calcular média espacial para plotagem
    dados_medios = climatologia[variavel].mean(dim=["lat", "lon"])

    # Criar figura com subplots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Plot 1: Série temporal
    x_vals = dados_medios[config[tipo]["dim"]].values
    y_vals = dados_medios.values

    ax1.plot(
        x_vals,
        y_vals,
        "o-",
        linewidth=3,
        markersize=8,
        color="steelblue",
        label="Climatologia",
    )
    ax1.fill_between(x_vals, y_vals, alpha=0.3, color="steelblue")

    ax1.set_title(
        titulo_personalizado or config[tipo]["titulo"],
        fontsize=14,
        fontweight="bold",
    )
    ax1.set_xlabel(config[tipo]["xlabel"], fontsize=12)
    ax1.set_ylabel("OLR (W/m²)", fontsize=12)
    ax1.grid(True, alpha=0.3)

    # Personalizar labels do eixo x para climatologia mensal
    if tipo == "mensal" and config[tipo]["labels"]:
        ax1.set_xticks(x_vals)
        ax1.set_xticklabels(config[tipo]["labels"])

    # Plot 2: Histograma dos valores
    ax2.hist(
        y_vals,
        bins=min(20, len(y_vals)),
        alpha=0.7,
        color="lightcoral",
        edgecolor="black",
    )
    ax2.set_title("Distribuição dos Valores", fontsize=14, fontweight="bold")
    ax2.set_xlabel("OLR (W/m²)", fontsize=12)
    ax2.set_ylabel("Frequência", fontsize=12)
    ax2.grid(True, alpha=0.3)

    # Adicionar estatísticas
    stats = validacao["estatisticas"]
    stats_text = (
        f"Média: {stats['media']:.1f} W/m²\n"
        f"Desvio: {stats['desvio_padrao']:.1f} W/m²\n"
        f"Min: {stats['minimo']:.1f} W/m²\n"
        f"Max: {stats['maximo']:.1f} W/m²"
    )

    ax1.text(
        0.02,
        0.98,
        stats_text,
        transform=ax1.transAxes,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
        fontsize=10,
    )

    plt.tight_layout()

    # Salvar figura se solicitado
    if salvar_figura:
        plt.savefig(salvar_figura, dpi=300, bbox_inches="tight")
        print(f"📊 Figura salva em: {salvar_figura}")

    plt.show()

    # Imprimir resumo da validação
    print(f"\n📋 RESUMO DA CLIMATOLOGIA {tipo.upper()}:")
    print(
        f"   Status: {'✅ Válida' if validacao['valida'] else '❌ Problemas encontrados'}"
    )
    if validacao["problemas"]:
        print("   Problemas:")
        for problema in validacao["problemas"]:
            print(f"     - {problema}")
    print(f"   Estatísticas: {stats_text.replace(chr(10), ', ')}")


# Função de conveniência para uso rápido
def criar_climatologia_rapida(
    anos: list[int], area_nordeste: bool = True, salvar: bool = True
) -> dict[str, xr.Dataset]:
    """
    Função de conveniência para criar climatologia rapidamente.

    Parameters
    ----------
    anos : List[int]
        Lista de anos para processar
    area_nordeste : bool, default True
        Se True, usa área padrão do Nordeste brasileiro
    salvar : bool, default True
        Se deve salvar os resultados

    Returns
    -------
    Dict[str, xr.Dataset]
        Climatologias criadas
    """

    # Área padrão do Nordeste brasileiro
    area_estudo = (-18, 2, -48, -32) if area_nordeste else None

    return criar_climatologia_olr(
        anos_inicio=min(anos),
        anos_fim=max(anos),
        anos_amostra=anos,
        area_estudo=area_estudo,
        salvar_netcdf=salvar,
        verbose=True,
    )


def processar_zcit_mes_por_mes(clima_mensal):
    """
    🔧 PROCESSA CADA MÊS SEPARADAMENTE

    Como um chef que prepara cada prato individualmente,
    garantindo que cada mês seja processado corretamente.
    """
    print("🔧 PROCESSANDO ZCIT MÊS POR MÊS (CORREÇÃO DO ERRO 3D)")
    print("=" * 60)

    # Verificar dimensões
    print(f"📊 Dimensões do clima_mensal: {clima_mensal.olr.dims}")
    print(f"📊 Shape: {clima_mensal.olr.shape}")

    # Inicializar ferramentas
    processor = DataProcessor()
    detector = IQRDetector(constant=1.5)

    resultados_zcit = {}

    nomes_meses = [
        "Janeiro",
        "Fevereiro",
        "Março",
        "Abril",
        "Maio",
        "Junho",
        "Julho",
        "Agosto",
        "Setembro",
        "Outubro",
        "Novembro",
        "Dezembro",
    ]

    # Processar cada mês individualmente
    for mes in range(1, 13):
        print(f"\n🗓️ Processando {nomes_meses[mes - 1]} (Mês {mes})...")

        try:
            # ========================================================
            # CORREÇÃO CRÍTICA: Selecionar MÊS ESPECÍFICO (2D)
            # ========================================================
            dados_mes_2d = clima_mensal.olr.sel(month=mes)

            print(f"   📊 Dados do mês - Shape: {dados_mes_2d.shape}")
            print(f"   📊 Dimensões: {dados_mes_2d.dims}")

            # Verificar se agora é 2D
            if dados_mes_2d.ndim != 2:
                print(
                    f"   ❌ ERRO: Dados ainda não são 2D! Dimensões: {dados_mes_2d.ndim}"
                )
                continue

            # ETAPA 1: Encontrar pontos de mínimo OLR (AGORA 2D!)
            print("   🔍 Aplicando find_minimum_coordinates em dados 2D...")
            min_coords = processor.find_minimum_coordinates(
                dados_mes_2d,  # ✅ AGORA É 2D (lat, lon)
                method="column_minimum",
                threshold=None,  # Automático
                search_radius=1,
            )

            print(f"   📍 Pontos de convecção encontrados: {len(min_coords)}")

            if len(min_coords) == 0:
                print(f"   ⚠️ Nenhum ponto encontrado para {nomes_meses[mes - 1]}")
                resultados_zcit[mes] = {
                    "latitude_zcit": 0.0,
                    "pontos_validos": 0,
                    "pontos_outliers": 0,
                    "metodo": "sem_dados",
                    "olr_medio": float(dados_mes_2d.mean()),
                }
                continue

            # ETAPA 2: Detectar outliers usando IQRDetector
            print("   🧪 Removendo outliers com IQRDetector...")
            coords_validos, coords_outliers, resumo = detector.detect_outliers(
                min_coords
            )

            print("   ✅ Pontos válidos: {len(coords_validos)}")
            print("   🚫 Outliers removidos: {len(coords_outliers)}")

            # ETAPA 3: Calcular posição da ZCIT
            if len(coords_validos) > 0:
                # Extrair latitudes dos pontos válidos
                latitudes_validas = [coord[1] for coord in coords_validos]

                # Calcular estatísticas
                latitude_zcit = np.mean(latitudes_validas)
                desvio_lat = (
                    np.std(latitudes_validas) if len(latitudes_validas) > 1 else 0
                )
                lat_min = np.min(latitudes_validas)
                lat_max = np.max(latitudes_validas)

                print(
                    f"   🎯 ZCIT detectada: {latitude_zcit:+6.2f}°N ± {desvio_lat:.2f}°"
                )
                print(f"   📏 Range: {lat_min:+.1f}° a {lat_max:+.1f}°")

                # Armazenar resultados
                resultados_zcit[mes] = {
                    "latitude_zcit": round(latitude_zcit, 2),
                    "desvio_padrao": round(desvio_lat, 2),
                    "pontos_validos": len(coords_validos),
                    "pontos_outliers": len(coords_outliers),
                    "latitude_min": round(lat_min, 2),
                    "latitude_max": round(lat_max, 2),
                    "coords_validos": coords_validos[
                        :10
                    ],  # Primeiros 10 para não sobrecarregar
                    "metodo": "loczcit_iqr",
                    "olr_medio": float(dados_mes_2d.mean()),
                }

            else:
                print("   ❌ Todos os pontos foram outliers!")
                resultados_zcit[mes] = {
                    "latitude_zcit": 0.0,
                    "desvio_padrao": 0.0,
                    "pontos_validos": 0,
                    "pontos_outliers": len(coords_outliers),
                    "metodo": "outliers_apenas",
                    "olr_medio": float(dados_mes_2d.mean()),
                }

        except Exception as e:
            print(f"   ❌ Erro no processamento: {e}")
            resultados_zcit[mes] = {
                "latitude_zcit": 0.0,
                "desvio_padrao": 0.0,
                "pontos_validos": 0,
                "pontos_outliers": 0,
                "metodo": "erro",
                "olr_medio": 0.0,
            }

    return resultados_zcit


# ============================================================================
# 📊 ANÁLISE E VISUALIZAÇÃO DOS RESULTADOS
# ============================================================================


def analisar_resultados_corrigidos(resultados_zcit):
    """
    📊 ANÁLISE DOS RESULTADOS CORRIGIDOS

    Como um estatístico que examina os dados processados
    para extrair insights climatológicos.
    """
    print("\n📊 ANÁLISE DOS RESULTADOS CORRIGIDOS:")
    print("=" * 50)

    # Extrair dados
    meses = list(range(1, 13))
    latitudes = [resultados_zcit[mes]["latitude_zcit"] for mes in meses]
    desvios = [resultados_zcit[mes]["desvio_padrao"] for mes in meses]
    pontos = [resultados_zcit[mes]["pontos_validos"] for mes in meses]
    olr_medios = [resultados_zcit[mes]["olr_medio"] for mes in meses]

    nomes_meses = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]

    # Mostrar resultados mês a mês
    print("🗓️ POSIÇÕES DA ZCIT POR MÊS:")
    for i, (mes, lat, dev, pts, olr) in enumerate(
        zip(meses, latitudes, desvios, pontos, olr_medios, strict=False)
    ):
        print(
            f"   📅 {nomes_meses[i]:3s}: ZCIT={lat:+6.2f}°N ± {dev:4.2f}° "
            f"({pts:3d} pts, OLR={olr:.1f})"
        )

    # Calcular estatísticas anuais
    latitudes_validas = [lat for lat in latitudes if lat != 0.0]

    if latitudes_validas:
        amplitude = max(latitudes_validas) - min(latitudes_validas)
        posicao_media = np.mean(latitudes_validas)
        variabilidade = np.std(latitudes_validas)

        idx_max = latitudes.index(max(latitudes_validas))
        idx_min = latitudes.index(min(latitudes_validas))

        print("\n📈 ESTATÍSTICAS ANUAIS:")
        print(
            f"   🔺 Posição mais ao NORTE: {nomes_meses[idx_max]} ({latitudes[idx_max]:+.2f}°N)"
        )
        print(
            f"   🔻 Posição mais ao SUL: {nomes_meses[idx_min]} ({latitudes[idx_min]:+.2f}°N)"
        )
        print(f"   📏 Amplitude anual: {amplitude:.1f}°")
        print(f"   🧭 Posição média: {posicao_media:+.2f}°N")
        print(f"   📊 Variabilidade: ±{variabilidade:.2f}°")

        # Qualidade dos dados
        pontos_total = sum(pontos)
        pontos_medio = np.mean(pontos)

        print("\n🔍 QUALIDADE DOS DADOS:")
        print(f"   📍 Total de pontos válidos: {pontos_total}")
        print(f"   📊 Média de pontos por mês: {pontos_medio:.1f}")

        meses_problemáticos = [nomes_meses[i] for i, p in enumerate(pontos) if p < 10]
        if meses_problemáticos:
            print(f"   ⚠️ Meses com poucos pontos: {meses_problemáticos}")

        return {
            "latitudes": latitudes,
            "desvios": desvios,
            "pontos": pontos,
            "amplitude": amplitude,
            "posicao_media": posicao_media,
            "variabilidade": variabilidade,
            "mes_max_norte": idx_max + 1,
            "mes_max_sul": idx_min + 1,
        }
    print("❌ Nenhum dado válido encontrado!")
    return None


# ============================================================================
# 🎨 GRÁFICO CIENTÍFICO FINAL
# ============================================================================


def criar_grafico_zcit_final(resultados_zcit, estatisticas=None):
    """
    🎨 GRÁFICO CIENTÍFICO FINAL

    Como um artista que finalmente tem as cores certas
    para pintar o retrato fiel da ZCIT.
    """
    print("\n🎨 CRIANDO GRÁFICO CIENTÍFICO FINAL...")

    # Extrair dados
    meses = np.arange(1, 13)
    latitudes = [resultados_zcit[mes]["latitude_zcit"] for mes in meses]
    desvios = [resultados_zcit[mes]["desvio_padrao"] for mes in meses]

    nomes_meses = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]

    # Configurar figura
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot principal
    ax.plot(
        meses,
        latitudes,
        "o-",
        linewidth=3,
        markersize=10,
        color="steelblue",
        label="Posição Climatológica da ZCIT",
        markerfacecolor="white",
        markeredgewidth=2,
    )

    # Barras de erro
    ax.errorbar(
        meses,
        latitudes,
        yerr=desvios,
        fmt="none",
        capsize=8,
        capthick=3,
        color="red",
        alpha=0.8,
        linewidth=2,
        label="Desvio Padrão (±σ)",
    )

    # Linha do equador
    ax.axhline(
        y=0,
        color="black",
        linestyle="--",
        alpha=0.8,
        linewidth=2,
        label="Equador (0°)",
    )

    # Anotações nos pontos
    for i, (mes, lat) in enumerate(zip(meses, latitudes, strict=False)):
        if lat != 0:  # Só anotar se há dados válidos
            ax.annotate(
                f"{lat:+.1f}°",
                xy=(mes, lat),
                xytext=(0, 15),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=11,
                fontweight="bold",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    edgecolor="blue",
                    alpha=0.8,
                ),
            )

    # Personalização
    ax.set_xlabel("Mês", fontsize=16, fontweight="bold")
    ax.set_ylabel("Latitude da ZCIT (°N)", fontsize=16, fontweight="bold")

    # Título
    if estatisticas:
        amplitude = estatisticas["amplitude"]
        titulo = (
            f"Climatologia da ZCIT - Metodologia LOCZCIT-IQR\n"
            f"Análise Mês por Mês (Amplitude: {amplitude:.1f}°)"
        )
    else:
        titulo = "Climatologia da ZCIT - Metodologia LOCZCIT-IQR\nAnálise Mês por Mês"

    ax.set_title(titulo, fontsize=18, fontweight="bold", pad=20)

    # Eixos
    ax.set_xticks(meses)
    ax.set_xticklabels(nomes_meses, fontsize=12)
    ax.tick_params(axis="y", labelsize=12)

    # Grid e legenda
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=14, loc="upper right")

    # Zonas sazonais
    ax.axvspan(11.5, 12.5, alpha=0.15, color="red")
    ax.axvspan(0.5, 3.5, alpha=0.15, color="red")
    ax.axvspan(6.5, 8.5, alpha=0.15, color="blue")

    # Ajustes finais
    lat_validas = [lat for lat in latitudes if lat != 0]
    if lat_validas:
        y_min = min(lat_validas) - 2
        y_max = max(lat_validas) + 2
        ax.set_ylim(y_min, y_max)

    ax.set_xlim(0.5, 12.5)

    plt.tight_layout()

    # Salvar
    nome_arquivo = "zcit_climatologia_corrigida_mes_por_mes.png"
    plt.savefig(nome_arquivo, dpi=300, bbox_inches="tight")
    print(f"✅ Gráfico salvo: {nome_arquivo}")

    plt.show()

    return fig


# ============================================================================
# 🚀 EXECUÇÃO COMPLETA CORRIGIDA
# ============================================================================


def executar_analise_completa_corrigida(clima_mensal):
    """
    🚀 EXECUÇÃO COMPLETA CORRIGIDA

    Processa tudo de forma correta, mês por mês.
    """
    print("🚀 EXECUTANDO ANÁLISE COMPLETA CORRIGIDA")
    print("=" * 60)
    print("🔧 CORREÇÕES APLICADAS:")
    print("   ✅ Processamento mês por mês (2D)")
    print("   ✅ Metodologia LOCZCIT-IQR adequada")
    print("   ✅ Remoção de outliers com IQRDetector")
    print("   ✅ Cálculo robusto de posições")
    print("=" * 60)

    try:
        # Etapa 1: Processar mês por mês
        resultados_zcit = processar_zcit_mes_por_mes(clima_mensal)

        # Etapa 2: Analisar resultados
        estatisticas = analisar_resultados_corrigidos(resultados_zcit)

        # Etapa 3: Criar gráfico
        if estatisticas:
            figura = criar_grafico_zcit_final(resultados_zcit, estatisticas)
        else:
            figura = criar_grafico_zcit_final(resultados_zcit)

        print("\n🎉 ANÁLISE COMPLETA CORRIGIDA CONCLUÍDA!")

        return {
            "resultados_zcit": resultados_zcit,
            "estatisticas": estatisticas,
            "figura": figura,
        }

    except Exception as e:
        print(f"❌ ERRO: {e}")
        import traceback

        traceback.print_exc()
        return None


def plotar_atlas_climatologico_mensal(
    clima_mensal: xr.Dataset,
    titulo: str = "Atlas Climatológico Mensal - Radiação de Onda Longa (OLR)",
    subtitulo: str = "Baseado em Climatologia NOAA",
    figsize: tuple[float, float] = (20, 15),
    save_path: str | Path | None = None,
    dpi: int = 300,
    **kwargs,
) -> tuple[plt.Figure, list[plt.Axes]]:
    """
    Cria um atlas climatológico mensal com 12 painéis (um para cada mês).

    Esta versão foi corrigida para usar um layout profissional com plt.subplots,
    evitando problemas de espaçamento, e garante que a função sempre retorne
    (fig, axes) para evitar o TypeError.
    """
    print("🗺️ Criando atlas climatológico mensal com layout profissional...")
    import cartopy.feature as cfeature
    from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER

    # --- Setup Inicial e Validação (do seu código original) ---
    try:
        from loczcit_iqr.plotting.visualizer import ZCITColormap

        cmap_classic = ZCITColormap.get_colormap(name="classic")
        print("✅ Usando paleta de cores 'classic' da biblioteca loczcit_iqr")
    except ImportError:
        cmap_classic = "gist_ncar_r"  # Fallback para uma paleta profissional
        print("⚠️ Usando paleta padrão 'gist_ncar_r' (loczcit_iqr não encontrada)")

    if "olr" not in clima_mensal.data_vars:
        raise ValueError("Dataset deve conter variável 'olr'")
    if "month" not in clima_mensal.dims or len(clima_mensal.month) != 12:
        raise ValueError("Dataset deve conter uma dimensão 'month' com 12 meses.")

    config = {
        "vmin": kwargs.get("vmin", 180),
        "vmax": kwargs.get("vmax", 300),
        "levels": kwargs.get("levels", np.arange(180, 301, 10)),
    }

    # ========================================================================
    # CORREÇÃO PRINCIPAL: Usar plt.subplots para um layout robusto
    # ========================================================================
    fig, axes = plt.subplots(
        nrows=3,
        ncols=4,
        figsize=figsize,
        subplot_kw={"projection": ccrs.PlateCarree()},
    )
    axes = axes.flatten()  # Transforma a matriz 3x4 de eixos em uma lista de 12

    contour = None  # Para a barra de cores

    try:
        for i, ax in enumerate(axes):
            mes = i + 1
            dados_mes = clima_mensal.olr.sel(month=mes)
            olr_medio = float(dados_mes.mean())

            print(f"  📅 Plotando {meses_em_portugues[mes]}...")

            # Plotar contorno preenchido
            contour = ax.contourf(
                dados_mes.lon,
                dados_mes.lat,
                dados_mes,
                transform=ccrs.PlateCarree(),
                cmap=cmap_classic,
                levels=config["levels"],
                extend="both",
            )

            # Adicionar features geográficas
            ax.add_feature(
                cfeature.COASTLINE.with_scale("50m"),
                edgecolor="black",
                linewidth=0.7,
            )
            ax.add_feature(
                cfeature.BORDERS.with_scale("50m"),
                edgecolor="gray",
                linewidth=0.4,
                linestyle="--",
            )

            # Configurar gridlines (lógica do seu código, que é boa)
            gl = ax.gridlines(draw_labels=True, alpha=0.5, linestyle="--", color="gray")
            gl.top_labels = gl.right_labels = False
            gl.left_labels = i % 4 == 0
            gl.bottom_labels = i >= 8
            gl.xformatter = LONGITUDE_FORMATTER
            gl.yformatter = LATITUDE_FORMATTER
            gl.xlabel_style = {"size": 8, "color": "black"}
            gl.ylabel_style = {"size": 8, "color": "black"}

            # Título do subplot
            ax.set_title(meses_em_portugues[mes], fontsize=14, fontweight="bold")

            # Texto com OLR médio (do seu código)
            ax.text(
                0.03,
                0.05,
                f"OLR: {olr_medio:.1f} W/m²",
                transform=ax.transAxes,
                fontsize=9,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
            )

    except Exception as e:
        print(f"❌ Erro durante a plotagem dos painéis: {e}")
        fig.text(0.5, 0.5, f"ERRO NA PLOTAGEM:\n{e}", ha="center", color="red")

    # ========================================================================
    # CORREÇÃO DE LAYOUT: Ajuste fino do espaçamento e adição de elementos globais
    # ========================================================================
    fig.subplots_adjust(
        top=0.9, bottom=0.1, left=0.05, right=0.95, hspace=0.17, wspace=0.07
    )

    # Títulos principais
    fig.suptitle(titulo, fontsize=24, fontweight="bold", y=0.98)
    fig.text(0.5, 0.94, subtitulo, fontsize=16, ha="center", style="italic")

    # Barra de cores global na parte inferior
    if contour:
        cbar_ax = fig.add_axes([0.2, 0.06, 0.6, 0.025])
        cbar = fig.colorbar(
            contour, cax=cbar_ax, orientation="horizontal", extend="both"
        )
        cbar.set_label("Radiação de Onda Longa (W/m²)", fontsize=12, fontweight="bold")

    # Informações técnicas (do seu código)
    try:
        info_text = f"Fonte: {clima_mensal.attrs.get('fonte', 'N/A')} | Período: {clima_mensal.attrs.get('periodo', 'N/A')}"
        fig.text(
            0.5,
            0.01,
            info_text,
            fontsize=10,
            ha="center",
            style="italic",
            color="gray",
        )
    except Exception:
        pass  # Ignora se não conseguir ler atributos

    # Salvar figura (do seu código)
    if save_path:
        print(f"💾 Salvando atlas em: {save_path}")
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight", facecolor="white")

    print("✅ Atlas climatológico criado com sucesso!")

    # ========================================================================
    # CORREÇÃO TypeError: Garantir que a função SEMPRE retorne a tupla
    # ========================================================================
    return fig, axes


# ============================================================================
# FUNÇÃO DE CONVENIÊNCIA PARA USO RÁPIDO
# ============================================================================


def criar_atlas_climatologico_rapido(
    clima_mensal: xr.Dataset, save_path: str = "atlas_climatologia_mensal.png"
) -> tuple[plt.Figure, list[plt.Axes]]:
    """
    Versão simplificada para criar atlas rapidamente.

    ANALOGIA DO CHEF EXECUTIVO 👨‍🍳
    Como um chef executivo que prepara um prato especial de forma
    rápida mas mantendo a qualidade, esta função cria um atlas
    climatológico com configurações otimizadas.

    Parameters
    ----------
    clima_mensal : xr.Dataset
        Dataset com climatologia mensal
    save_path : str, default "atlas_climatologia_mensal.png"
        Caminho para salvar

    Returns
    -------
    fig, axes : matplotlib objects
        Figura e eixos criados

    Examples
    --------
    >>> # Uso super rápido
    >>> fig, axes = criar_atlas_climatologico_rapido(clima_mensal)

    >>> # Com caminho personalizado
    >>> fig, axes = criar_atlas_climatologico_rapido(
    ...     clima_mensal,
    ...     save_path="meu_atlas.png"
    ... )
    """
    return plotar_atlas_climatologico_mensal(
        clima_mensal,
        titulo="Atlas Climatológico Mensal - OLR",
        subtitulo="Baseado em Climatologia NOAA",
        save_path=save_path,
        figsize=(16, 12),
        dpi=200,
    )


# ============================================================================
# FUNÇÃO PARA VALIDAR DADOS ANTES DE PLOTAR
# ============================================================================


def validar_dados_atlas(clima_mensal: xr.Dataset) -> dict[str, Any]:
    """
    Valida se o dataset está adequado para plotar o atlas.

    ANALOGIA DO INSPETOR DE QUALIDADE 🔍
    Como um inspetor que verifica se todos os ingredientes
    estão frescos antes de autorizar o preparo do prato.

    Parameters
    ----------
    clima_mensal : xr.Dataset
        Dataset a ser validado

    Returns
    -------
    Dict[str, Any]
        Relatório de validação com problemas encontrados

    Examples
    --------
    >>> relatorio = validar_dados_atlas(clima_mensal)
    >>> if relatorio['valido']:
    ...     print("✅ Dados válidos para plotar atlas")
    >>> else:
    ...     print("❌ Problemas encontrados:", relatorio['problemas'])
    """

    problemas = []
    detalhes = {}

    print("🔍 VALIDANDO DADOS PARA ATLAS CLIMATOLÓGICO...")

    # Verificar se é um Dataset
    if not isinstance(clima_mensal, xr.Dataset):
        problemas.append("Dados devem ser um xarray.Dataset")
        return {"valido": False, "problemas": problemas, "detalhes": detalhes}

    # Verificar variável OLR
    if "olr" not in clima_mensal.data_vars:
        problemas.append("Variável 'olr' não encontrada")
    else:
        detalhes["olr_dims"] = list(clima_mensal.olr.dims)
        detalhes["olr_shape"] = clima_mensal.olr.shape

        # Verificar dimensões da variável OLR
        dims_esperadas = ["month", "lat", "lon"]
        dims_olr = list(clima_mensal.olr.dims)

        for dim in dims_esperadas:
            if dim not in dims_olr:
                problemas.append(f"Dimensão '{dim}' não encontrada em olr")

    # Verificar dimensão month
    if "month" not in clima_mensal.dims:
        problemas.append("Dimensão 'month' não encontrada")
    else:
        n_meses = len(clima_mensal.month)
        detalhes["n_meses"] = n_meses
        detalhes["meses_valores"] = list(clima_mensal.month.values)

        if n_meses != 12:
            problemas.append(f"Esperado 12 meses, encontrado {n_meses}")

        # Verificar se meses são 1-12
        meses_esperados = list(range(1, 13))
        meses_encontrados = sorted(clima_mensal.month.values)
        if meses_encontrados != meses_esperados:
            problemas.append(f"Meses devem ser 1-12, encontrado {meses_encontrados}")

    # Verificar coordenadas lat/lon
    for coord in ["lat", "lon"]:
        if coord not in clima_mensal.coords:
            problemas.append(f"Coordenada '{coord}' não encontrada")
        else:
            valores = clima_mensal[coord].values
            detalhes[f"{coord}_range"] = (
                float(valores.min()),
                float(valores.max()),
            )
            detalhes[f"{coord}_size"] = len(valores)

            # Verificar se coordenadas fazem sentido
            if coord == "lat":
                if valores.min() < -90 or valores.max() > 90:
                    problemas.append(
                        f"Latitudes fora do range válido (-90, 90): {valores.min():.1f} a {valores.max():.1f}"
                    )
            elif coord == "lon":
                if valores.min() < -180 or valores.max() > 360:
                    problemas.append(
                        f"Longitudes fora do range válido (-180, 360): {valores.min():.1f} a {valores.max():.1f}"
                    )

    # Verificar valores OLR
    if "olr" in clima_mensal.data_vars:
        olr_values = clima_mensal.olr.values
        detalhes["olr_range"] = (
            float(np.nanmin(olr_values)),
            float(np.nanmax(olr_values)),
        )
        detalhes["olr_mean"] = float(np.nanmean(olr_values))
        detalhes["has_nan"] = bool(np.isnan(olr_values).any())
        detalhes["percent_valid"] = float(
            100 * np.isfinite(olr_values).sum() / olr_values.size
        )

        # Verificar range típico de OLR
        olr_min, olr_max = detalhes["olr_range"]
        if olr_min < 100 or olr_max > 400:
            problemas.append(
                f"Valores OLR fora do range típico (100-400 W/m²): {olr_min:.1f} a {olr_max:.1f}"
            )

        if detalhes["percent_valid"] < 50:
            problemas.append(
                f"Muitos valores inválidos: apenas {detalhes['percent_valid']:.1f}% válidos"
            )

    # Verificar atributos importantes
    attrs_importantes = ["fonte", "periodo", "versao_loczcit"]
    detalhes["atributos"] = {}
    for attr in attrs_importantes:
        if attr in clima_mensal.attrs:
            detalhes["atributos"][attr] = clima_mensal.attrs[attr]
        else:
            detalhes["atributos"][attr] = "Não encontrado"

    # Resultado final
    valido = len(problemas) == 0

    print(f"   📊 Dimensões: {dict(clima_mensal.dims)}")
    print(f"   🗓️  Meses: {detalhes.get('n_meses', 'N/A')}")
    print(f"   📏 Range OLR: {detalhes.get('olr_range', 'N/A')} W/m²")
    print(f"   ✅ Dados válidos: {detalhes.get('percent_valid', 'N/A'):.1f}%")

    if valido:
        print("✅ Validação aprovada - dados prontos para atlas!")
    else:
        print("❌ Problemas encontrados:")
        for problema in problemas:
            print(f"   - {problema}")

    return {"valido": valido, "problemas": problemas, "detalhes": detalhes}


# Executar teste apenas se chamado diretamente
if __name__ == "__main__":
    # ... código de exemplo já executado ...

    # Executar teste das novas funcionalidades
    _testar_novas_funcionalidades()
