"""
loczcit_iqr/plotting/visualizer.py

Módulo para visualização da metodologia Loczcit-IQR.
Fornece classes e funções intuitivas para criar visualizações profissionais
dos resultados da análise ZCIT.

Melhorias implementadas:
- Interface mais intuitiva com métodos simplificados
- Configurações predefinidas para casos comuns
- Melhor tratamento de erros e mensagens informativas
- Suporte aprimorado para diferentes formatos de saída
- Integração direta com os módulos core da biblioteca
- Templates de visualização prontos para uso
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import xarray as xr
from cartopy.mpl.gridliner import LATITUDE_FORMATTER, LONGITUDE_FORMATTER
from geopy.distance import distance as geodistance
from matplotlib import patheffects
from matplotlib.offsetbox import AnchoredText, AnnotationBbox, OffsetImage
from matplotlib_scalebar.scalebar import ScaleBar
from shapely.geometry import (
    LineString,
    MultiLineString,
    Point,
    Polygon,
)

# Configurar logger
logger = logging.getLogger(__name__)

# Verificar disponibilidade dos módulos loczcit_iqr
try:
    from loczcit_iqr.core import DataProcessor, IQRDetector, SplineInterpolator
    from loczcit_iqr.utils import pentada_to_dates

    LOCZCIT_AVAILABLE = True
except ImportError:
    LOCZCIT_AVAILABLE = False

# Obter o caminho absoluto do script atual (__file__)
script_path = Path(__file__).resolve()

# Navegar para o diretório raiz do projeto (loczcit_iqr)
# script_path.parent é 'plotting', script_path.parent.parent é 'loczcit_iqr'
project_root = script_path.parent.parent


class ZCITColormap:
    """
    Classe aprimorada para gerenciar colormaps personalizados para visualização OLR.

    Analogia: Como um artista que organiza suas paletas de cores em diferentes
    estilos - clássico, moderno, alto contraste - cada um adequado para
    diferentes propósitos e públicos.
    """

    # Paletas predefinidas
    PALETTES = {
        "classic": [
            "#3b71a1",
            "#407bb3",
            "#4483c2",
            "#4e92c7",
            "#569fcc",
            "#61aac9",
            "#66b8c4",
            "#6bc7bc",
            "#78d6a4",
            "#84e38c",
            "#8bed6b",
            "#abf056",
            "#c6f24b",
            "#dbf547",
            "#eef743",
            "#fcf942",
            "#ffef3b",
            "#ffe436",
            "#fcd32d",
            "#fcbf23",
            "#faab19",
            "#f79811",
            "#f5820f",
            "#f26a0f",
            "#ed590e",
            "#e84315",
            "#d93523",
            "#c92435",
            "#b5163e",
            "#a11045",
            "#8f0d47",
            "#800a45",
            "#61063b",
            "#520436",
            "#470334",
            "#3d022e",
            "#330128",
        ],
        "modern": "viridis_r",
        "high_contrast": "RdBu_r",
        "grayscale": "gray_r",
        "rainbow": "rainbow",
        "thermal": "hot_r",
    }

    @classmethod
    def get_colormap(
        cls,
        name: str = "classic",
        reverse: bool = False,
        n_colors: int | None = None,
    ) -> mcolors.Colormap:
        """
        Retorna colormap com opções de personalização.

        Parameters
        ----------
        name : str
            Nome da paleta ('classic', 'modern', 'high_contrast', etc.)
        reverse : bool
            Se True, inverte a paleta
        n_colors : int, optional
            Número de cores discretas (None para contínuo)

        Returns
        -------
        matplotlib.colors.Colormap
            Colormap configurado
        """
        if name not in cls.PALETTES:
            logger.warning(f"Paleta '{name}' não encontrada. Usando 'classic'.")
            name = "classic"

        palette = cls.PALETTES[name]

        if isinstance(palette, list):
            # Paleta customizada
            if reverse:
                palette = palette[::-1]
            # N=None cria colormap contínuo, número específico cria discreto
            cmap = mcolors.LinearSegmentedColormap.from_list(
                f"olr_{name}",
                palette,
                N=n_colors if n_colors is not None else 256,
            )
            cmap.set_over("#000000")
            cmap.set_under("#417CA7")
        else:
            # Paleta matplotlib
            cmap = plt.cm.get_cmap(palette, n_colors)
            if reverse:
                cmap = cmap.reversed()

        return cmap

    @classmethod
    def preview_palettes(cls, figsize: tuple[float, float] = (12, 8)):
        """Exibe preview de todas as paletas disponíveis."""
        n_palettes = len(cls.PALETTES)
        fig, axes = plt.subplots(n_palettes, 1, figsize=figsize)

        # Dados de exemplo
        data = np.linspace(180, 295, 100).reshape(1, -1)

        for ax, (name, _) in zip(axes, cls.PALETTES.items(), strict=False):
            cmap = cls.get_colormap(name)
            ax.imshow(data, aspect="auto", cmap=cmap)
            ax.set_title(f"Paleta: {name}")
            ax.set_yticks([])
            ax.set_xticks([180, 220, 260, 295])
            ax.set_xlabel("OLR (W/m²)")

        plt.tight_layout()
        return fig


class ZCITVisualizer:
    """
    Classe principal aprimorada para visualização dos resultados da análise ZCIT.

    Analogia: Como um estúdio de design completo que não apenas cria mapas,
    mas oferece templates prontos, assistentes de configuração e ferramentas
    para personalização avançada.
    """

    # Templates de visualização predefinidos
    TEMPLATES = {
        "publication": {
            "figsize": (12, 10),
            "dpi": 300,
            "font_size": 12,
            "title_size": 16,
            "colormap": "classic",
            "grid": True,
            "coastlines": True,
            "borders": True,
        },
        "presentation": {
            "figsize": (16, 12),
            "dpi": 150,
            "font_size": 14,
            "title_size": 20,
            "colormap": "modern",
            "grid": True,
            "coastlines": True,
            "borders": False,
        },
        "web": {
            "figsize": (10, 8),
            "dpi": 100,
            "font_size": 10,
            "title_size": 14,
            "colormap": "high_contrast",
            "grid": False,
            "coastlines": True,
            "borders": False,
        },
        "report": {
            "figsize": (8, 6),
            "dpi": 150,
            "font_size": 10,
            "title_size": 12,
            "colormap": "classic",
            "grid": True,
            "coastlines": True,
            "borders": True,
        },
    }

    def __init__(
        self,
        template: str = "publication",
        projection: ccrs.Projection | None = None,
        **kwargs,
    ):
        """
        Inicializa o visualizador com template predefinido.

        Parameters
        ----------
        template : str
            Template de visualização ('publication', 'presentation', 'web', 'report')
        projection : cartopy.crs.Projection, optional
            Projeção cartográfica (padrão: PlateCarree)
        **kwargs
            Parâmetros adicionais para sobrescrever o template
        """
        # Carregar configurações do template
        if template in self.TEMPLATES:
            self.config = self.TEMPLATES[template].copy()
        else:
            logger.warning(
                f"Template '{template}' não encontrado. Usando 'publication'."
            )
            self.config = self.TEMPLATES["publication"].copy()

        # Atualizar com kwargs
        self.config.update(kwargs)

        # Configurações básicas
        self.figsize = self.config.get("figsize", (12, 10))
        self.projection = projection or ccrs.PlateCarree()
        self.fig = None
        self.ax = None
        self.colormap = ZCITColormap.get_colormap(
            self.config.get("colormap", "classic")
        )

        # Configurar matplotlib
        self._setup_matplotlib()

        # Cache para dados
        self._data_cache = {}

    def _setup_matplotlib(self):
        """Configura parâmetros globais do matplotlib."""
        plt.rcParams.update(
            {
                "font.size": self.config.get("font_size", 12),
                "font.family": "serif",
                "figure.dpi": self.config.get("dpi", 150),
                "savefig.dpi": self.config.get("dpi", 150),
                "savefig.bbox": "tight",
                "savefig.pad_inches": 0.1,
            }
        )

    def quick_plot(
        self,
        data: xr.DataArray,
        pentada: int,
        zcit_coords: list[tuple[float, float]] | None = None,
        title: str | None = None,
        save_path: str | None = None,
        **kwargs,
    ) -> tuple[plt.Figure, plt.Axes]:
        """
        Método simplificado para criar visualização rápida.

        Parameters
        ----------
        data : xr.DataArray
            Dados OLR
        pentada : int
            Número da pentada
        zcit_coords : list, optional
            Coordenadas da ZCIT
        title : str, optional
            Título personalizado
        save_path : str, optional
            Caminho para salvar
        **kwargs
            Parâmetros adicionais

        Returns
        -------
        fig, ax : matplotlib Figure e Axes

        Example
        -------
        >>> viz = ZCITVisualizer()
        >>> fig, ax = viz.quick_plot(olr_data, pentada=30,
        ...                          zcit_coords=coords,
        ...                          save_path='zcit_p30.png')
        """
        # Criar figura
        self.create_figure()

        # Plotar OLR
        self.plot_olr_field(data, pentada, **kwargs)

        # Adicionar features geográficas
        if self.config.get("coastlines", True):
            self.add_geographic_features()

        # Plotar ZCIT se fornecida
        if zcit_coords:
            self.plot_zcit_coordinates(zcit_coords)

        # Configurar grade
        if self.config.get("grid", True):
            self.setup_gridlines()

        # Título
        if title:
            self.ax.set_title(
                title,
                fontsize=self.config.get("title_size", 16),
                fontweight="bold",
                pad=15,
            )
        else:
            self.add_default_title(pentada)

        # Adicionar elementos informativos
        self.add_info_elements()

        # Salvar se solicitado
        if save_path:
            self.save(save_path)

        return self.fig, self.ax

    def create_figure(
        self, figsize: tuple[float, float] | None = None
    ) -> tuple[plt.Figure, plt.Axes]:
        """
        Cria a figura e os eixos com configurações otimizadas.
        """
        figsize = figsize or self.figsize

        self.fig, self.ax = plt.subplots(
            figsize=figsize,
            subplot_kw=dict(projection=self.projection),
            facecolor="white",
        )

        # Configurar aspecto
        self.ax.set_aspect("auto")

        return self.fig, self.ax

    def plot_olr_field(
        self,
        data: xr.DataArray | xr.Dataset,
        pentada: int | None = None,
        levels: np.ndarray | None = None,
        cbar_config: dict | None = None,
        **kwargs,
    ) -> Any:
        """
        Plota campo de OLR com opções avançadas.

        Parameters
        ----------
        data : xr.DataArray ou xr.Dataset
            Dados OLR
        pentada : int, optional
            Pentada específica (se data for Dataset)
        levels : array, optional
            Níveis de contorno customizados
        cbar_config : dict, optional
            Configuração da barra de cores
        **kwargs
            Argumentos adicionais para contourf
        """
        # Preparar dados
        if isinstance(data, xr.Dataset):
            if "olr" not in data:
                raise ValueError("Dataset deve conter variável 'olr'")
            olr_data = data["olr"]
        else:
            olr_data = data

        # Selecionar pentada se necessário
        if pentada is not None and "pentada" in olr_data.dims:
            olr_data = olr_data.sel(pentada=pentada)
            self._data_cache["current_pentada"] = pentada

        # Níveis padrão otimizados para OLR
        if levels is None:
            levels = np.arange(180, 300, 5)  # Incremento de 5 W/m²

        # Plotar contorno
        contour = self.ax.contourf(
            olr_data.lon,
            olr_data.lat,
            olr_data,
            transform=ccrs.PlateCarree(),
            cmap=self.colormap,
            levels=levels,
            extend="both",
            **kwargs,
        )

        # Configurar barra de cores
        cbar_config = cbar_config or {}
        cbar = self._add_optimized_colorbar(contour, **cbar_config)

        # Armazenar referências
        self._data_cache["olr_contour"] = contour
        self._data_cache["colorbar"] = cbar

        return contour

    def _add_optimized_colorbar(
        self,
        contour,
        position: list[float] | None = None,
        orientation: str = "horizontal",
        label: str = "OLR [W/m²]",
        ticks: list[float] | None = None,
        **kwargs,
    ):
        """Adiciona barra de cores otimizada."""
        # Posição padrão inteligente
        if position is None:
            if orientation == "horizontal":
                position = [0.15, 0.08, 0.7, 0.03]
            else:
                position = [0.92, 0.15, 0.03, 0.7]

        # Criar eixo para colorbar
        cbar_ax = self.fig.add_axes(position)

        # Criar colorbar
        cbar = plt.colorbar(
            contour,
            cax=cbar_ax,
            orientation=orientation,
            ticks=ticks or contour.levels[::2],  # Ticks a cada 2 níveis
        )

        # Estilizar
        cbar.outline.set_linewidth(1)
        cbar.ax.tick_params(labelsize=10, width=1, length=5)

        # Label
        label_kwargs = {"fontsize": 11, "fontweight": "bold"}
        label_kwargs.update(kwargs)
        cbar.set_label(label, **label_kwargs)

        return cbar

    def add_geographic_features(
        self,
        resolution: str = "50m",
        land_color: str = "lightgray",
        ocean_color: str | None = None,
        borders: bool = True,
        rivers: bool = False,
        lakes: bool = False,
        UF: bool = True,
    ):
        """
        Adiciona features geográficas com Cartopy.

        Parameters
        ----------
        resolution : str
            Resolução das features ('10m', '50m', '110m')
        land_color : str
            Cor dos continentes
        ocean_color : str, optional
            Cor dos oceanos
        borders : bool
            Se adiciona fronteiras
        rivers : bool
            Se adiciona rios
        lakes : bool
            Se adiciona lagos
        """
        # Adicionar oceanos
        if ocean_color:
            self.ax.add_feature(
                cfeature.OCEAN.with_scale(resolution),
                color=ocean_color,
                zorder=0,
            )

        # Adicionar terra
        self.ax.add_feature(
            cfeature.LAND.with_scale(resolution),
            facecolor=land_color,
            edgecolor="black",
            linewidth=0.5,
            zorder=1,
        )

        # Adicionar linhas de costa
        self.ax.add_feature(
            cfeature.COASTLINE.with_scale(resolution),  # <-- FIX
            edgecolor="black",
            linewidth=1,
            zorder=10,
        )

        # Adicionar fronteiras
        if borders and self.config.get("borders", True):
            self.ax.add_feature(
                cfeature.BORDERS.with_scale(resolution),  # <-- FIX
                edgecolor="gray",
                linewidth=0.5,
                linestyle="--",
                zorder=5,
            )

        # Adicionar rios
        if rivers:
            self.ax.add_feature(
                cfeature.RIVERS.with_scale(resolution),  # <-- FIX
                edgecolor="blue",
                linewidth=0.5,
                zorder=5,
            )

        # Adicionar lagos
        if lakes:
            self.ax.add_feature(
                cfeature.LAKES.with_scale(resolution),  # <-- FIX
                facecolor="lightblue",
                edgecolor="blue",
                linewidth=0.5,
                zorder=5,
            )

        # Adicionar Unidades Federativas (UF) #loczcit_iqr\data\shapefiles\UFs_BR.parquet
        if UF:
            uf_path = project_root / "data" / "shapefiles" / "UFs_BR.parquet"
            if uf_path.exists():
                try:
                    print(f"Carregando UFs de: {uf_path}")
                    ufs = gpd.read_parquet(uf_path)
                    self.ax.add_geometries(
                        ufs.geometry,
                        crs=ccrs.PlateCarree(),
                        edgecolor="black",
                        facecolor="none",
                        linewidth=0.5,
                        zorder=5,
                    )
                except Exception:
                    logger.error(f"Arquivo não encontrado em: {uf_path}")

    def plot_zcit_analysis(
        self,
        coords_valid: list[tuple[float, float]],
        coords_outliers: list[tuple[float, float]],
        zcit_line: LineString | None = None,
        std_value: float | None = None,
        study_area: str | Path | Polygon | None = None,
        interpolation_method: str = "bspline",
    ):
        """
        Plota análise completa da ZCIT incluindo outliers e interpolação.

        Parameters
        ----------
        coords_valid : list
            Coordenadas válidas
        coords_outliers : list
            Coordenadas outliers
        zcit_line : LineString, optional
            Linha ZCIT interpolada
        std_value : float, optional
            Desvio padrão para linhas de limite
        study_area : various, optional
            Área de estudo
        interpolation_method : str
            Método de interpolação a usar
        """
        # Plotar coordenadas válidas
        if coords_valid:
            self.plot_zcit_coordinates(
                coords_valid, color="green", label="ZCIT Válida", marker="o"
            )

        # Plotar outliers
        if coords_outliers:
            self.plot_zcit_coordinates(
                coords_outliers,
                color="red",
                label="Outliers",
                marker="x",
                s=50,
            )

        # Criar linha interpolada se não fornecida
        if zcit_line is None and coords_valid and LOCZCIT_AVAILABLE:
            try:
                interpolator = SplineInterpolator(default_method=interpolation_method)
                zcit_line, _ = interpolator.interpolate(coords_valid)
            except Exception as e:
                logger.error(f"Erro na interpolação: {e}")

        # Plotar linhas
        if zcit_line and std_value is not None:
            # Processar área de estudo
            if isinstance(study_area, (str, Path)):
                study_area = self._load_study_area(study_area)

            self.plot_zcit_lines(zcit_line, std_value, study_area)

    def plot_zcit_coordinates(
        self,
        coordinates: list[tuple[float, float]],
        label: str = "ZCIT",
        color: str = "black",
        marker: str = "o",
        s: float = 36,
        edge_color: str | None = None,
        edge_width: float = 1,
        add_buffer: bool = True,
        **kwargs,
    ):
        """
        Plota coordenadas com estilo aprimorado.
        """
        if not coordinates:
            return None

        lons = [coord[0] for coord in coordinates]
        lats = [coord[1] for coord in coordinates]

        # Efeito de contorno
        path_effects = []

        if edge_color is None:
            path_effects = [patheffects.withStroke(linewidth=0)]

        if add_buffer and edge_color:
            path_effects = [patheffects.withStroke(linewidth=3, foreground=edge_color)]

        scatter = self.ax.scatter(
            lons,
            lats,
            color=color,
            edgecolor=edge_color,
            linewidth=edge_width,
            s=s,
            marker=marker,
            zorder=10,
            path_effects=path_effects,
            label=label,
            alpha=0.8,
            transform=ccrs.PlateCarree(),
            **kwargs,
        )

        return scatter

    def plot_linestring(
        self,
        geom: LineString | MultiLineString,
        color: str,
        linestyle: str,
        label: str,
        **kwargs,
    ):
        """
        Plota uma geometria LineString ou MultiLineString no mapa.

        Parameters
        ----------
        geom : LineString ou MultiLineString
            A geometria a ser plotada.
        color : str
            A cor da linha.
        linestyle : str
            O estilo da linha (ex: 'solid', 'dashed').
        label : str
            O rótulo para a legenda.
        **kwargs
            Argumentos adicionais para ax.add_geometries.
        """
        if geom is None or geom.is_empty:
            return

        # Garante que a geometria esteja em uma lista para add_geometries
        geometries = (
            [geom] if isinstance(geom, (LineString, Point)) else list(geom.geoms)
        )

        # Adiciona a geometria ao eixo do mapa
        self.ax.add_geometries(
            geometries,
            crs=ccrs.PlateCarree(),
            edgecolor=color,
            facecolor="none",
            linestyle=linestyle,
            label=label,
            **kwargs,
        )

    def plot_study_area(
        self,
        study_area_path: str
        | Path
        | gpd.GeoDataFrame
        | None = None,  # <-- 1. TORNADO OPCIONAL
        facecolor: str = "none",
        edgecolor: str = "purple",
        linewidth: float = 2.0,
        linestyle: str = "--",
        label: str = "Área de Estudo",
        **kwargs,
    ):
        """
        Desenha o contorno da área de estudo no mapa.

        Se 'study_area_path' for None, usa o caminho padrão da biblioteca.
        """
        try:
            # <-- 2. LÓGICA PARA CARREGAR O CAMINHO PADRÃO --- INÍCIO ---
            path_to_process = study_area_path

            if path_to_process is None:
                logger.info("Nenhum caminho fornecido. Usando área de estudo padrão.")
                # Constrói o caminho padrão de forma robusta a partir da localização do script
                current_dir = Path(__file__).parent  # Pasta 'plotting'
                default_path = (
                    current_dir.parent.parent  # Sobe para a pasta 'src'
                    / "data"
                    / "shapefiles"
                    / "Area_LOCZCIT.parquet"
                )
                path_to_process = default_path
            # <-- LÓGICA PARA CARREGAR O CAMINHO PADRÃO --- FIM ---

            if isinstance(path_to_process, gpd.GeoDataFrame):
                study_area_geom = path_to_process.geometry.union_all()
            else:
                # Usa o método interno para carregar o arquivo (seja o padrão ou o fornecido)
                study_area_geom = self._load_study_area(path_to_process)

            if study_area_geom and not study_area_geom.is_empty:
                self.ax.add_geometries(
                    [study_area_geom],
                    crs=ccrs.PlateCarree(),
                    facecolor=facecolor,
                    edgecolor=edgecolor,
                    linewidth=linewidth,
                    linestyle=linestyle,
                    label=label,
                    zorder=20,
                    **kwargs,
                )
                logger.info(
                    f"Área de estudo de '{path_to_process}' plotada com sucesso."
                )
        except Exception as e:
            logger.error(f"Não foi possível plotar a área de estudo: {e}")

    def plot_zcit_lines(
        self,
        zcit_line: LineString,
        std_value: float,
        study_area: Polygon | None = None,
        colors: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
        **kwargs,
    ):
        """
        Plota linhas ZCIT com configurações customizáveis.
        """
        # Cores e labels padrão
        if colors is None:
            colors = {"mean": "green", "plus_std": "red", "minus_std": "blue"}

        if labels is None:
            labels = {
                "mean": "Posição Média",
                "plus_std": "+1 Desvio Padrão",
                "minus_std": "-1 Desvio Padrão",
            }

        # Criar linhas com desvio padrão
        lons_line, lats_line = zip(*zcit_line.coords, strict=False)
        zcit_plus_std = LineString(
            zip(lons_line, [lat + std_value for lat in lats_line], strict=False)
        )
        zcit_minus_std = LineString(
            zip(lons_line, [lat - std_value for lat in lats_line], strict=False)
        )

        # Recortar se área de estudo fornecida
        if study_area and not study_area.is_empty:
            zcit_line_clipped = zcit_line.intersection(study_area)
            zcit_plus_std_clipped = zcit_plus_std.intersection(study_area)
            zcit_minus_std_clipped = zcit_minus_std.intersection(study_area)
        else:
            zcit_line_clipped = zcit_line
            zcit_plus_std_clipped = zcit_plus_std
            zcit_minus_std_clipped = zcit_minus_std

        # Plotar as três linhas
        self.plot_linestring(
            zcit_line_clipped,
            colors["mean"],
            "solid",
            labels["mean"],
            linewidth=3,
        )
        self.plot_linestring(
            zcit_plus_std_clipped,
            colors["plus_std"],
            "dashdot",
            labels["plus_std"],
            linewidth=2,
        )
        self.plot_linestring(
            zcit_minus_std_clipped,
            colors["minus_std"],
            "dashed",
            labels["minus_std"],
            linewidth=2,
        )

    def setup_gridlines(
        self,
        xlims: tuple[float, float] | None = None,
        ylims: tuple[float, float] | None = None,
        x_interval: float | None = None,
        y_interval: float | None = None,
        **kwargs,
    ):
        """
        Configura grade com detecção automática de intervalos.
        """
        # Limites automáticos se não fornecidos
        if xlims is None:
            xlims = self.ax.get_xlim()
        if ylims is None:
            ylims = self.ax.get_ylim()

        # Intervalos inteligentes
        if x_interval is None:
            x_range = xlims[1] - xlims[0]
            x_interval = self._calculate_nice_interval(x_range)

        if y_interval is None:
            y_range = ylims[1] - ylims[0]
            y_interval = self._calculate_nice_interval(y_range)

        # Aplicar limites
        self.ax.set_xlim(xlims)
        self.ax.set_ylim(ylims)

        # Criar gridlines
        gl = self.ax.gridlines(
            crs=ccrs.PlateCarree(),
            draw_labels=True,
            alpha=0.5,
            linestyle="--",
            linewidth=0.5,
            **kwargs,
        )

        # Configurar labels
        gl.top_labels = False
        gl.bottom_labels = True
        gl.left_labels = True
        gl.right_labels = False
        gl.xpadding = 2
        gl.ypadding = 2

        # Formatadores
        gl.xformatter = LONGITUDE_FORMATTER
        gl.yformatter = LATITUDE_FORMATTER

        # Localizadores
        x_ticks = np.arange(xlims[0], xlims[1] + x_interval, x_interval)
        y_ticks = np.arange(ylims[0], ylims[1] + y_interval, y_interval)
        gl.xlocator = mticker.FixedLocator(x_ticks)
        gl.ylocator = mticker.FixedLocator(y_ticks)

        # Estilo dos labels
        gl.xlabel_style = {
            "size": self.config.get("font_size", 12),
            "color": "black",
        }
        gl.ylabel_style = {
            "size": self.config.get("font_size", 12),
            "color": "black",
        }

        return gl

    def _calculate_nice_interval(self, range_value: float) -> float:
        """Calcula intervalo 'bonito' para eixos."""
        if range_value <= 0:
            return 1.0

        # Intervalos preferenciais
        nice_intervals = [0.5, 1, 2, 2.5, 5, 10, 15, 20, 25, 30, 45, 60]

        # Número ideal de divisões
        target_divisions = 6
        ideal_interval = range_value / target_divisions

        # Encontrar intervalo mais próximo
        for interval in nice_intervals:
            if interval >= ideal_interval * 0.8:
                return interval

        return nice_intervals[-1]

    def add_info_elements(
        self,
        stats_box: bool = True,
        outliers_box: bool = True,
        legend: bool = True,
        credits: bool = True,
        scale_bar: bool = False,
        north_arrow: bool = False,
    ):
        """
        Adiciona elementos informativos de forma modular.
        """
        if stats_box and "olr_contour" in self._data_cache:
            self.add_statistics_box()

        if outliers_box:
            # Buscar outliers no cache ou parâmetros
            outliers = self._data_cache.get("outliers", [])
            if outliers:
                self.add_outliers_box(outliers)

        if legend:
            self.add_legend()

        if credits:
            self.add_credits()

        if scale_bar:
            self.add_scale_bar()

        if north_arrow:
            self.add_north_arrow()

    def add_statistics_box(self, location: str = "upper left"):
        """Adiciona uma caixa com estatísticas do campo OLR de forma robusta."""
        try:
            # --- FIX STARTS HERE ---

            # 1. Extrai os dados válidos do contorno como um array 1D.
            #    .compressed() remove os pontos mascarados (fora do contorno).
            contour = self._data_cache.get("olr_contour")
            if contour is None:
                logger.warning(
                    "Dados de contorno não encontrados no cache para estatísticas."
                )
                return

            valid_data = contour.get_array().compressed()

            # 2. Converte para float64 para garantir precisão numérica e evitar overflow.
            valid_data = valid_data.astype(np.float64)

            # --- FIX ENDS HERE ---

            if valid_data.size == 0:
                logger.warning(
                    "Nenhum dado válido no contorno para calcular estatísticas."
                )
                return

            # Calcula estatísticas com os dados corrigidos
            mean_val = np.mean(valid_data)
            min_val = np.min(valid_data)
            max_val = np.max(valid_data)
            std_val = np.std(valid_data)

            # Formata o texto para exibição
            stats_text = (
                f"Estatísticas OLR\n"
                f"-------------------\n"
                f"Média: {mean_val:>7.2f} W/m²\n"
                f"Mín:   {min_val:>7.2f} W/m²\n"
                f"Máx:   {max_val:>7.2f} W/m²\n"
                f"DP:    {std_val:>7.2f} W/m²"
            )

            # Cria a caixa de texto ancorada
            at = AnchoredText(
                stats_text,
                loc=location,
                frameon=True,
                prop=dict(size=8, family="monospace"),
            )
            at.patch.set_boxstyle("round,pad=0.5,rounding_size=0.2")
            at.patch.set_facecolor(
                "rgba(255, 255, 240, 0.8)"
            )  # Ivory com transparência
            at.patch.set_edgecolor("black")
            self.ax.add_artist(at)

        except KeyError:
            logger.warning(
                "Chave 'olr_contour' não encontrada no cache. Não é possível adicionar estatísticas."
            )
        except Exception as e:
            logger.warning(f"Não foi possível adicionar a caixa de estatísticas: {e}")

    def add_outliers_box(
        self, outliers: list[tuple[float, float]], location: str = "upper left"
    ):
        """Adiciona uma caixa informando o número de outliers."""
        try:
            num_outliers = len(outliers)
            outliers_text = f"Outliers Detectados: {num_outliers}"

            at = AnchoredText(
                outliers_text,
                loc=location,
                frameon=True,
                prop=dict(size=10, weight="bold", color="red"),
            )
            at.patch.set_boxstyle("round,pad=0.4")
            at.patch.set_facecolor("white")
            at.patch.set_alpha(0.7)
            self.ax.add_artist(at)
        except Exception as e:
            logger.warning(f"Não foi possível adicionar a caixa de outliers: {e}")

    def add_legend(
        self,
        loc="best",
        loc_geo=None,
        fontsize=10,
        framealpha=0.7,
        ncol=1,
        title=None,
        proxies_config=None,
        **kwargs,
    ):
        """
        Adiciona uma legenda robusta e compatível com todos os elementos do mapa, com proxies personalizáveis.

        Parameters:
        -----------
        loc : str, optional
            Localização padrão da legenda ('best', 'upper right', etc.). Ignorado se loc_geo for fornecido.
        loc_geo : tuple, optional
            Tupla com (latitude, longitude) para posicionar a legenda em coordenadas geográficas.
        fontsize : int, optional
            Tamanho da fonte da legenda.
        framealpha : float, optional
            Opacidade do fundo da legenda.
        ncol : int, optional
            Número de colunas na legenda.
        title : str, optional
            Título da legenda.
        proxies_config : list of dict, optional
            Lista de dicionários com configurações dos proxies. Cada dicionário pode conter:
                - type: 'Line2D' ou 'Patch' (padrão: 'Line2D')
                - marker: marcador para Line2D (ex.: 'o', 'x', '*')
                - color: cor do marcador ou linha (ex.: 'green', 'red')
                - label: rótulo do elemento na legenda
                - linewidth: espessura da linha (para Line2D)
                - linestyle: estilo da linha (ex.: '-', '--', '-.')
                - edgecolor: cor da borda (para Patch)
                - facecolor: cor de preenchimento (para Patch)
                - markersize: tamanho do marcador (para Line2D)
        **kwargs : dict
            Argumentos adicionais para matplotlib.legend.
        """
        from matplotlib.lines import Line2D
        from matplotlib.patches import Patch

        # Configuração padrão da legenda
        legend_config = {
            "fontsize": fontsize,
            "frameon": True,
            "facecolor": "white",
            "edgecolor": "black",
            "framealpha": framealpha,
            "ncol": ncol,
            "title": title,
        }
        legend_config.update(kwargs)

        # Proxies padrão (usados se proxies_config não for fornecido)
        default_proxies = [
            {
                "type": "Line2D",
                "marker": "o",
                "color": "green",
                "label": "ZCIT Válida",
                "linestyle": "",
                "markersize": 8,
            },
            {
                "type": "Line2D",
                "marker": "x",
                "color": "red",
                "label": "Outliers",
                "linestyle": "",
                "markersize": 8,
            },
            {
                "type": "Line2D",
                "marker": "*",
                "color": "yellow",
                "label": "Sistemas Isolados",
                "linestyle": "",
                "markersize": 10,
                "markeredgecolor": "black",
                "markeredgewidth": 0.5,
            },
            {
                "type": "Line2D",
                "color": "green",
                "label": "Posição Média da ZCIT",
                "linestyle": "-",
                "linewidth": 2,
            },
            {
                "type": "Line2D",
                "color": "red",
                "label": "Limite Superior (+2°)",
                "linestyle": "-.",
                "linewidth": 2,
            },
            {
                "type": "Line2D",
                "color": "blue",
                "label": "Limite Inferior (-2°)",
                "linestyle": "--",
                "linewidth": 2,
            },
            {
                "type": "Patch",
                "facecolor": "none",
                "edgecolor": "orange",
                "label": "Área de Busca",
                "linestyle": "--",
                "linewidth": 1.5,
            },
        ]

        # Usar proxies_config se fornecido, caso contrário usar default_proxies
        proxies_config = (
            proxies_config if proxies_config is not None else default_proxies
        )

        # Criar proxies com base nas configurações
        proxies = []
        for config in proxies_config:
            proxy_type = config.get("type", "Line2D")
            label = config.get("label", "Sem Rótulo")

            if proxy_type == "Line2D":
                proxies.append(
                    Line2D(
                        [0],
                        [0],
                        marker=config.get("marker", ""),
                        color=config.get("color", "black"),
                        linestyle=config.get("linestyle", "-"),
                        linewidth=config.get("linewidth", 1),
                        markersize=config.get("markersize", 8),
                        label=label,
                    )
                )
            elif proxy_type == "Patch":
                proxies.append(
                    Patch(
                        facecolor=config.get("facecolor", "none"),
                        edgecolor=config.get("edgecolor", "black"),
                        linestyle=config.get("linestyle", "-"),
                        linewidth=config.get("linewidth", 1),
                        label=label,
                    )
                )

        if loc_geo is not None:
            # Extrair latitude e longitude
            lon, lat = loc_geo

            # Converter coordenadas geográficas para coordenadas de dados
            data_coords = self.ax.transData.transform((lon, lat))

            # Converter coordenadas de dados para coordenadas normalizadas (0 a 1)
            inv = self.ax.transAxes.inverted()
            normalized_coords = inv.transform(data_coords)

            # Configurar a legenda com bbox_to_anchor para posicionamento em coordenadas normalizadas
            legend_config["loc"] = "center"
            legend_config["bbox_to_anchor"] = normalized_coords
            legend_config["bbox_transform"] = self.ax.transAxes
        else:
            # Usar a localização padrão (loc)
            legend_config["loc"] = loc

        # Criar legenda com proxies
        legend = self.ax.legend(handles=proxies, **legend_config)

        # Definir o zorder da legenda
        legend.set_zorder(20)

        # Ajustar tamanho dos marcadores na legenda (opcional)
        for handle in legend.legend_handles:
            if isinstance(handle, Line2D):
                handle.set_markersize(handle.get_markersize() or 8)

        return legend

    def add_logo(
        self,
        logo_path=None,
        position="upper right",
        loc_geo=None,
        zoom=0.2,
        alpha=1.0,
        margin=(0.02, 0.02, 0.02, 0.02),
        zorder=20,
    ):
        """
        Adiciona uma logo ao gráfico com posicionamento avançado e margens personalizadas.

        Parameters:
        -----------
        logo_path : str, optional
            Caminho para o arquivo de imagem da logo. Se None, usa o caminho padrão.
        position : str, optional
            Posição da logo ('best', 'upper right', 'upper left', 'lower left',
            'lower right', 'right', 'center left', 'center right', 'lower center',
            'upper center', 'center'). Padrão: 'upper right'.
        loc_geo : tuple, optional
            Tupla (longitude, latitude) para posicionar a logo. Padrão: None.
        zoom : float, optional
            Fator de escala da logo. Padrão: 0.2.
        alpha : float, optional
            Opacidade da logo (0.0 a 1.0). Padrão: 1.0.
        margin : float or tuple, optional
            Margem para afastar a logo das bordas.
            - Se for um número (ex: 0.02), aplica a mesma margem em todos os lados.
            - Se for uma tupla/lista (ex: (0.1, 0.02, 0.1, 0.02)), aplica as
              margens na ordem (top, right, bottom, left).
            Padrão: (0.02, 0.02, 0.02, 0.02).
        zorder : int or float, optional
            Ordem de renderização da logo. Padrão: 20.
        """
        # Define o caminho padrão e carrega a imagem
        # Path(__file__).parent pega o diretório do arquivo atual (plotting)
        current_dir = Path(__file__).parent

        # .parent.parent sobe dois níveis (para src) e / concatena o resto do caminho
        default_logo_path = (
            current_dir.parent.parent / "assets" / "img" / "logo_Oficial.png"
        )

        logo_file = str(logo_path) if logo_path is not None else str(default_logo_path)
        try:
            logo_array = mpimg.imread(logo_file)
        except FileNotFoundError:
            print(f"Arquivo de logo não encontrado: {logo_file}. Usando placeholder.")
            # Usando uma URL de placeholder que funciona com mpimg.imread
            import urllib

            try:
                with urllib.request.urlopen(
                    "https://drive.google.com/uc?export=view&id=1TSJo9W4Sd4xHl_eLgEdBA4RjBGvevKYh"
                ) as url:
                    logo_array = plt.imread(url, format="png")
            except Exception as e:
                print(f"Não foi possível carregar o placeholder. Erro: {e}")
                return  # Aborta a função se não houver imagem

        imagebox = OffsetImage(logo_array, zoom=zoom, alpha=alpha)

        # Posicionamento por coordenadas geográficas (lógica inalterada)
        if loc_geo is not None:
            lon, lat = loc_geo
            data_coords = self.ax.transData.transform((lon, lat))
            xy = self.ax.transAxes.inverted().transform(data_coords)
            xycoords = "axes fraction"
            box_alignment = (0.5, 0.5)
        else:
            # ################################################################ #
            # ##              NOVA LÓGICA PARA PROCESSAR MARGENS            ## #
            # ################################################################ #
            if isinstance(margin, (int, float)):
                # Se for um número único, usa para todos os lados
                margin_top = margin_right = margin_bottom = margin_left = margin
            elif isinstance(margin, (list, tuple)) and len(margin) == 4:
                # Se for uma tupla/lista, desempacota os valores
                margin_top, margin_right, margin_bottom, margin_left = margin
            else:
                raise ValueError(
                    "O parâmetro 'margin' deve ser um número ou uma tupla/lista de 4 números."
                )

            # Mapeamento de posições usando as margens individuais
            position_map = {
                "upper right": (1 - margin_right, 1 - margin_top),
                "upper left": (margin_left, 1 - margin_top),
                "lower left": (margin_left, margin_bottom),
                "lower right": (1 - margin_right, margin_bottom),
                "right": (1 - margin_right, 0.5),
                "center left": (margin_left, 0.5),
                "center right": (1 - margin_right, 0.5),  # Alias para 'right'
                "lower center": (0.5, margin_bottom),
                "upper center": (0.5, 1 - margin_top),
                "center": (0.5, 0.5),
            }
            position_map["best"] = position_map["upper right"]

            # Mapeamento do alinhamento da caixa (lógica inalterada)
            box_alignment_map = {
                "upper right": (1, 1),
                "upper left": (0, 1),
                "lower left": (0, 0),
                "lower right": (1, 0),
                "right": (1, 0.5),
                "center left": (0, 0.5),
                "center right": (1, 0.5),
                "lower center": (0.5, 0),
                "upper center": (0.5, 1),
                "center": (0.5, 0.5),
            }
            box_alignment_map["best"] = box_alignment_map["upper right"]

            if position not in position_map:
                raise ValueError(
                    f"Posição inválida: {position}. Use: {list(position_map.keys())}"
                )

            xy = position_map[position]
            box_alignment = box_alignment_map[position]
            xycoords = "axes fraction"

        # Cria e adiciona a AnnotationBbox (lógica inalterada)
        ab = AnnotationBbox(
            imagebox,
            xy,
            xycoords=xycoords,
            boxcoords="axes fraction",
            box_alignment=box_alignment,
            frameon=False,
            pad=0.0,
            zorder=zorder,
        )
        self.ax.add_artist(ab)

    def add_credits(
        self,
        source: str = "NOAA",  # "NOAA", "ERA5" ou "ECMWF"
        custom_text: str | None = None,
        location: tuple[float, float] = (0.99, 0.01),
        fontsize: int = 12,
        color: str = "white",
        **kwargs,
    ):
        """
        Adiciona créditos no canto da figura com suporte para múltiplas fontes.

        Parameters
        ----------
        source : str
            Fonte de dados: "NOAA", "ERA5" ou "ECMWF"
        custom_text : str, optional
            Texto customizado (sobrescreve o padrão)
        location : tuple
            Posição do texto (x, y) em coordenadas normalizadas
        fontsize : int
            Tamanho da fonte
        color : str
            Cor do texto
        **kwargs
            Argumentos adicionais para ax.text
        """
        # Textos predefinidos para cada fonte
        CREDIT_TEXTS = {
            "NOAA": "\nSource: NOAA HIRS L1B, Gridsat CDR",
            "ERA5": "\nSource: ERA5 Reanalysis, ECMWF",
            "ECMWF": "\nSource: ECMWF IFS Operational Forecast",
            "ECMWF IFS FORECAST": "\nSource: ECMWF IFS Operational Forecast",  # Suporte para o nome completo usado no seu script
        }

        try:
            # Determinar o texto a ser usado
            if custom_text:
                text = custom_text
            else:
                source_upper = source.upper()

                # Verificação flexível: se "ECMWF" estiver na string, usa a legenda do ECMWF
                if "ECMWF" in source_upper and source_upper not in CREDIT_TEXTS:
                    source_key = "ECMWF"
                elif source_upper in CREDIT_TEXTS:
                    source_key = source_upper
                else:
                    logger.warning(
                        f"Fonte '{source}' não reconhecida. Usando 'NOAA' como padrão."
                    )
                    source_key = "NOAA"

                text = CREDIT_TEXTS[source_key]

            # Configurações padrão
            text_config = {
                "transform": self.ax.transAxes,
                "fontsize": fontsize,
                "color": color,
                "fontweight": "bold",
                "fontstyle": "italic",
                "ha": "right",
                "va": "bottom",
            }

            # Atualizar com kwargs
            text_config.update(kwargs)

            # Adicionar o texto
            self.ax.text(location[0], location[1], text, **text_config)

            logger.info(f"Créditos adicionados: {text.strip()}")

        except Exception as e:
            logger.warning(f"Não foi possível adicionar os créditos: {e}")

    def add_scale_bar(
        self,
        dist: float | None = None,
        units: str = "km",
        location: str = "lower right",
        length_fraction: float = 0.2,
        scale_loc: str = "bottom",
        rotation: str = "horizontal-only",
        font_properties: dict | None = None,
        zorder: float = 10,
        study_area: str | Path | gpd.GeoDataFrame | None = None,
        loc_geo: tuple[float, float] | None = None,
    ) -> None:
        """
        Adiciona uma barra de escala métrica (km ou m) a um mapa em CRS geográfico (graus).
        - Se 'dist' for None, calcula a distância (em metros) de 1° de longitude
        na latitude média do mapa ou da área de estudo.
        - Se 'loc_geo' (lon, lat) for fornecido, posiciona a escala nessa coordenada.
        """
        try:
            # 1) Obter os limites em lon/lat
            if study_area is not None:
                if isinstance(study_area, gpd.GeoDataFrame):
                    gdf = study_area.to_crs("EPSG:4326")
                else:
                    gdf = self._load_study_area(study_area).to_crs("EPSG:4326")
                lon_min, lat_min, lon_max, lat_max = gdf.total_bounds
            else:
                lon_min, lon_max, lat_min, lat_max = self.ax.get_extent(
                    crs=ccrs.PlateCarree()
                )

            # 2) Latitude média para cálculo de distâncias
            lat_avg = 0.5 * (lat_min + lat_max)

            # 3) Calcular dist em metros se não fornecido
            if dist is None:
                p1 = (lat_avg, 0)
                p2 = (lat_avg, 1.0)
                # Usando geodist para calcular a distância em metros para 1 grau de longitude
                dist_m = geodistance(p1, p2).meters
            else:
                dist_m = dist

            # 4) Criar a ScaleBar (usando a abordagem robusta que deixa a biblioteca auto-ajustar a unidade)
            scalebar = ScaleBar(
                dist_m,  # Valor sempre em metros
                location=location,
                length_fraction=length_fraction,
                scale_loc=scale_loc,
                rotation=rotation,
                font_properties=font_properties or {"family": "serif", "size": "large"},
            )
            scalebar.set_zorder(zorder)
            self.ax.add_artist(scalebar)

            # 5) Reposicionar usando coordenadas geográficas, se fornecido
            if loc_geo is not None:
                lon, lat = loc_geo
                # Converte coordenadas geográficas (dados) para coordenadas de eixo (0 a 1)
                ax_coord = self.ax.transAxes.inverted().transform(
                    self.ax.transData.transform((lon, lat))
                )

                # --- INÍCIO DA CORREÇÃO ---
                # Define o sistema de coordenadas de referência para a âncora
                scalebar.set_bbox_transform(self.ax.transAxes)
                # Define a posição da âncora usando as coordenadas convertidas
                scalebar.set_bbox_to_anchor(ax_coord)
                # --- FIM DA CORREÇÃO ---

                # A localização (ex: 'center') define qual canto da caixa da escala
                # será alinhado com o ponto de âncora.
                scalebar.loc = location

        except Exception as e:
            # Log do erro para depuração
            logging.error(f"Erro ao adicionar barra de escala: {e}", exc_info=True)
            raise

    def add_north_arrow(
        self,
        north_arrow_path=None,
        position="upper right",
        loc_geo=None,
        zoom=0.15,
        alpha=1.0,
        margin=(0.02, 0.02, 0.02, 0.02),
        zorder=12,
    ):
        """
        Adiciona uma rosa dos ventos (norte) ao mapa com margens personalizadas.

        Parameters:
        -----------
        north_arrow_path : str, optional
            Caminho para o arquivo PNG da rosa dos ventos. Se None, usa o padrão.
        position : str, optional
            Posição da rosa dos ventos ('best', 'upper right', 'upper left', etc.).
            Padrão: "upper right".
        loc_geo : tuple, optional
            Tupla (longitude, latitude) para posicionar a rosa dos ventos.
        zoom : float, optional
            Fator de escala da rosa dos ventos. Padrão: 0.15.
        alpha : float, optional
            Opacidade da rosa dos ventos (0.0 a 1.0). Padrão: 1.0.
        margin : float or tuple, optional
            Margem para afastar a rosa dos ventos das bordas.
            - Se for um número (ex: 0.02), aplica a mesma margem em todos os lados.
            - Se for uma tupla/lista (ex: (0.1, 0.02, 0.1, 0.02)), aplica as
              margens na ordem (top, right, bottom, left).
            Padrão: (0.02, 0.02, 0.02, 0.02).
        zorder : int or float, optional
            Ordem de renderização da rosa dos ventos. Padrão: 12.
        """
        # Define o caminho padrão e carrega a imagem (código inalterado)
        current_dir = Path(__file__).parent

        default_north_arrow_path = (
            current_dir.parent.parent / "assets" / "img" / "North_Arrow_139.png"
        )

        north_arrow_file = (
            str(north_arrow_path)
            if north_arrow_path is not None
            else str(default_north_arrow_path)
        )
        try:
            north_arrow_array = mpimg.imread(north_arrow_file)
        except FileNotFoundError:
            print(
                f"Arquivo da rosa dos ventos não encontrado: {north_arrow_file}. Usando placeholder."
            )
            # Usando uma URL de placeholder que funciona com mpimg.imread
            import urllib

            try:
                with urllib.request.urlopen(
                    "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f2/Arrow-north.svg/1200px-Arrow-north.svg.png"
                ) as url:
                    north_arrow_array = plt.imread(url, format="png")
            except Exception as e:
                print(f"Não foi possível carregar o placeholder. Erro: {e}")
                return  # Aborta a função se não houver imagem

        imagebox = OffsetImage(north_arrow_array, zoom=zoom, alpha=alpha)

        # Posicionamento por coordenadas geográficas (lógica inalterada)
        if loc_geo is not None:
            lon, lat = loc_geo
            data_coords = self.ax.transData.transform((lon, lat))
            xy = self.ax.transAxes.inverted().transform(data_coords)
            xycoords = "axes fraction"
            box_alignment = (0.5, 0.5)
        else:
            if isinstance(margin, (int, float)):
                # Se for um número único, usa para todos os lados
                margin_top = margin_right = margin_bottom = margin_left = margin
            elif isinstance(margin, (list, tuple)) and len(margin) == 4:
                # Se for uma tupla/lista, desempacota os valores
                margin_top, margin_right, margin_bottom, margin_left = margin
            else:
                raise ValueError(
                    "O parâmetro 'margin' deve ser um número ou uma tupla/lista de 4 números."
                )

            # Mapeamento de posições usando as margens individuais
            position_map = {
                "upper right": (1 - margin_right, 1 - margin_top),
                "upper left": (margin_left, 1 - margin_top),
                "lower left": (margin_left, margin_bottom),
                "lower right": (1 - margin_right, margin_bottom),
                "right": (1 - margin_right, 0.5),
                "center left": (margin_left, 0.5),
                "center right": (1 - margin_right, 0.5),  # Alias para 'right'
                "lower center": (0.5, margin_bottom),
                "upper center": (0.5, 1 - margin_top),
                "center": (0.5, 0.5),
            }
            position_map["best"] = position_map["upper right"]

            # Mapeamento do alinhamento da caixa (lógica inalterada)
            box_alignment_map = {
                "upper right": (1, 1),
                "upper left": (0, 1),
                "lower left": (0, 0),
                "lower right": (1, 0),
                "right": (1, 0.5),
                "center left": (0, 0.5),
                "center right": (1, 0.5),
                "lower center": (0.5, 0),
                "upper center": (0.5, 1),
                "center": (0.5, 0.5),
            }
            box_alignment_map["best"] = box_alignment_map["upper right"]

            if position not in position_map:
                raise ValueError(
                    f"Posição inválida: {position}. Use: {list(position_map.keys())}"
                )

            xy = position_map[position]
            box_alignment = box_alignment_map[position]
            xycoords = "axes fraction"

        # Cria e adiciona a AnnotationBbox (lógica inalterada)
        ab = AnnotationBbox(
            imagebox,
            xy,
            xycoords=xycoords,
            boxcoords="axes fraction",
            box_alignment=box_alignment,
            frameon=False,
            pad=0.0,
            zorder=zorder,
        )
        self.ax.add_artist(ab)

    def add_default_title(self, pentada: int | None = None, year: int | None = None):
        """Adiciona título padrão inteligente."""
        parts = ["Análise ZCIT"]

        if pentada:
            parts.append(f"Pentada {pentada}")
            if year:
                # Calcular período da pentada
                try:
                    start_date, end_date = pentada_to_dates(pentada, year)
                    parts.append(
                        f"({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')})"
                    )
                except Exception:
                    parts.append(f"de {year}")
        elif year:
            parts.append(f"Ano {year}")

        title = " - ".join(parts)
        self.ax.set_title(
            title,
            fontsize=self.config.get("title_size", 16),
            fontweight="bold",
            pad=15,
        )

    def save(
        self,
        filename: str | Path,
        dpi: int | None = None,
        bbox_inches: str = "tight",
        transparent: bool = False,
        metadata: dict | None = None,
        **kwargs,
    ):
        """
        Salva figura com opções avançadas.

        Parameters
        ----------
        filename : str or Path
            Nome do arquivo
        dpi : int, optional
            Resolução (usa config se None)
        bbox_inches : str
            Ajuste de bordas
        transparent : bool
            Fundo transparente
        metadata : dict, optional
            Metadados para incluir no arquivo
        **kwargs
            Argumentos adicionais para savefig
        """
        if self.fig is None:
            raise ValueError(
                "Nenhuma figura para salvar. Crie uma visualização primeiro."
            )

        # Resolver caminho
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # DPI da configuração ou parâmetro
        dpi = dpi or self.config.get("dpi", 300)

        # Metadados
        if metadata:
            self.fig.canvas.manager.set_window_title(json.dumps(metadata))

        # Salvar
        self.fig.savefig(
            filepath,
            dpi=dpi,
            bbox_inches=bbox_inches,
            transparent=transparent,
            facecolor="white" if not transparent else "none",
            **kwargs,
        )

        logger.info(f"Figura salva: {filepath} (DPI: {dpi})")

        # Retornar caminho absoluto
        return filepath.absolute()

    def _load_study_area(self, path: str | Path) -> Polygon | None:
        """Carrega área de estudo de arquivo."""
        try:
            path = Path(path)
            if path.suffix == ".parquet":
                gdf = gpd.read_parquet(path)
            else:
                gdf = gpd.read_file(path)

            if not gdf.empty:
                return gdf.geometry.union_all()
        except Exception as e:
            logger.error(f"Erro ao carregar área de estudo: {e}")

        return None

    def close(self):
        """Fecha a figura e limpa memória."""
        if self.fig:
            plt.close(self.fig)
            self.fig = None
            self.ax = None
        self._data_cache.clear()

    def plot_complete_analysis(
        self,
        olr_data: xr.DataArray,
        title: str,
        coords_valid: list | None = None,
        coords_outliers: list | None = None,
        sistemas_convectivos: list | None = None,
        zcit_line: LineString | None = None,
        study_area_visible: bool = True,
        credits: str = "NOAA",
        save_path: str | None = None,
    ) -> tuple[plt.Figure, plt.Axes]:
        """
        Cria uma visualização completa da análise ZCIT com todos os elementos.

        Parameters
        ----------
        olr_data : xr.DataArray
            Campo 2D de OLR para ser plotado no fundo.
        title : str
            O título principal do gráfico.
        coords_valid : list, optional
            Lista de coordenadas válidas da ZCIT.
        coords_outliers : list, optional
            Lista de coordenadas de outliers.
        sistemas_convectivos : list, optional
            Lista de coordenadas de sistemas convectivos isolados.
        zcit_line : LineString, optional
            A linha interpolada da ZCIT.
        study_area_visible : bool, default True
            Se True, plota a área de estudo padrão.
        credits : str, default "NOAA"
            Fonte de dados: "NOAA", "ERA5" ou texto customizado
        save_path : str, optional
            Se fornecido, salva a figura no caminho especificado.

        Returns
        -------
        tuple[plt.Figure, plt.Axes]
            A figura e os eixos do Matplotlib gerados.

        Examples
        --------
        >>> # Usando dados NOAA (padrão)
        >>> viz.plot_complete_analysis(olr_data, title="Análise ZCIT")

        >>> # Usando dados ERA5
        >>> viz.plot_complete_analysis(
        ...     olr_data,
        ...     title="Análise ZCIT",
        ...     credits="ERA5"
        ... )

        >>> # Usando texto customizado
        >>> viz.plot_complete_analysis(
        ...     olr_data,
        ...     title="Análise ZCIT",
        ...     credits="Fonte: Meus Dados Customizados"
        ... )
        """
        print("\nIniciando a criação da visualização completa...")

        # --- Etapa de Configuração ---
        self.create_figure(figsize=(15, 7))
        config_barra_cores = {"position": [0.15, 0.05, 0.7, 0.03]}

        # --- 1. Plotar Camadas Base ---
        self.plot_olr_field(data=olr_data, pentada=None, cbar_config=config_barra_cores)
        self.add_geographic_features()
        if study_area_visible:
            self.plot_study_area(
                study_area_path=None,
                edgecolor="orange",
                linestyle="--",
                linewidth=1.5,
                label="Área de Busca",
            )

        # --- 2. Plotar Pontos da Análise ---
        if coords_valid:
            self.plot_zcit_coordinates(
                coords_valid, color="green", marker="o", label="ZCIT Válida"
            )
        if sistemas_convectivos:
            self.plot_zcit_coordinates(
                sistemas_convectivos,
                color="yellow",
                marker="*",
                s=60,
                label="Sistemas Isolados",
            )
        if coords_outliers:
            self.plot_zcit_coordinates(
                coords_outliers, color="red", marker="x", s=50, label="Outliers"
            )

        # --- 3. Plotar Linhas da ZCIT ---
        if zcit_line:
            self.plot_zcit_lines(
                zcit_line=zcit_line,
                std_value=2,
                colors={"mean": "green", "plus_std": "red", "minus_std": "blue"},
                labels={
                    "mean": "Posição Média da ZCIT",
                    "plus_std": "Limite Superior (+2°)",
                    "minus_std": "Limite Inferior (-2°)",
                },
            )

        # --- 4. Configurar Elementos Finais ---
        self.setup_gridlines(
            xlims=(-80, 0), ylims=(-12, 17), x_interval=2, y_interval=2
        )
        self.ax.set_title(title, fontsize=16, fontweight="bold", pad=15)

        # Adicionar elementos decorativos
        self.add_legend(
            loc="lower left", title="Legenda", fontsize=9, framealpha=1, ncol=1
        )

        # <-- MUDANÇA AQUI: Usar o novo parâmetro credits
        self.add_credits(source=credits)

        self.add_logo(loc_geo=(-5, 13), zoom=0.1, alpha=0.8)
        self.add_north_arrow(loc_geo=(-73.5, 0.4), zoom=0.1, alpha=1, zorder=12)
        self.add_scale_bar(
            units="km",
            location="center",
            loc_geo=(-73.5, -2.2),
            length_fraction=0.08,
            scale_loc="bottom",
            zorder=20,
        )

        # --- 5. Salvar e Retornar ---
        if save_path:
            self.save(save_path)
            print(f"💾 Figura salva em: {save_path}")

        print("✅ Visualização completa pronta.")
        return self.fig, self.ax


class ZCITPlotter:
    """
    Classe de alto nível para criar visualizações ZCIT com uma interface simples.

    Analogia: Como um assistente pessoal que conhece suas preferências e
    pode criar visualizações complexas com comandos simples.
    """

    def __init__(
        self,
        data_processor: Optional["DataProcessor"] = None,
        default_template: str = "publication",
    ):
        """
        Inicializa o plotter.

        Parameters
        ----------
        data_processor : DataProcessor, optional
            Instância do processador de dados
        default_template : str
            Template padrão para visualizações
        """
        self.processor = data_processor
        self.default_template = default_template
        self.figures = []  # Registro de figuras criadas

    def plot_pentada(
        self,
        olr_data: xr.Dataset,
        pentada: int,
        year: int,
        find_zcit: bool = True,
        detect_outliers: bool = True,
        interpolate: bool = True,
        template: str | None = None,
        save_path: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Cria visualização completa de uma pentada.

        Parameters
        ----------
        olr_data : xr.Dataset
            Dados OLR
        pentada : int
            Número da pentada
        year : int
            Ano
        find_zcit : bool
            Se deve encontrar coordenadas ZCIT
        detect_outliers : bool
            Se deve detectar outliers
        interpolate : bool
            Se deve interpolar linha ZCIT
        template : str, optional
            Template de visualização
        save_path : str, optional
            Caminho para salvar
        **kwargs
            Parâmetros adicionais

        Returns
        -------
        dict
            Resultados incluindo figura, coordenadas, estatísticas
        """
        results = {
            "pentada": pentada,
            "year": year,
            "coords_valid": [],
            "coords_outliers": [],
            "zcit_line": None,
            "statistics": {},
            "figure": None,
        }

        # Criar visualizador
        viz = ZCITVisualizer(template=template or self.default_template)

        # Criar figura base
        viz.create_figure()

        # Plotar OLR
        viz.plot_olr_field(olr_data, pentada)

        # Adicionar features geográficas
        viz.add_geographic_features()

        # Encontrar ZCIT se solicitado
        if find_zcit and self.processor:
            try:
                # Encontrar mínimos
                min_coords = self.processor.find_minimum_coordinates(
                    olr_data["olr"].sel(pentada=pentada)
                )

                if min_coords and detect_outliers:
                    # Detectar outliers
                    if LOCZCIT_AVAILABLE:
                        detector = IQRDetector()
                        (
                            coords_valid,
                            coords_outliers,
                            stats,
                        ) = detector.detect_outliers(min_coords)
                        results["coords_valid"] = coords_valid
                        results["coords_outliers"] = coords_outliers
                        results["statistics"]["iqr"] = stats
                    else:
                        results["coords_valid"] = min_coords
                else:
                    results["coords_valid"] = min_coords

                # Interpolar se houver coordenadas válidas
                if (
                    interpolate
                    and results["coords_valid"]
                    and len(results["coords_valid"]) >= 3
                ):
                    if LOCZCIT_AVAILABLE:
                        interpolator = SplineInterpolator()
                        zcit_line, interp_stats = interpolator.interpolate(
                            results["coords_valid"]
                        )
                        results["zcit_line"] = zcit_line
                        results["statistics"]["interpolation"] = interp_stats

                # Plotar análise ZCIT
                viz.plot_zcit_analysis(
                    results["coords_valid"],
                    results["coords_outliers"],
                    results["zcit_line"],
                    results["statistics"].get("iqr", {}).get("std"),
                )

            except Exception as e:
                logger.error(f"Erro na análise ZCIT: {e}")

        # Configurar grade e elementos
        viz.setup_gridlines()
        viz.add_default_title(pentada, year)
        viz.add_info_elements()

        # Salvar se solicitado
        if save_path:
            viz.save(save_path)

        # Armazenar figura
        results["figure"] = viz.fig
        self.figures.append(viz.fig)

        return results

    def plot_hovmoller_daily(
        self,
        daily_data: xr.Dataset,
        longitude: float,
        cmap: str = "classic",
        figsize: tuple[float, float] = (12, 8),
        x_tick_interval_days: int = 5,
        y_tick_interval: float = 2.5,
        ylims: tuple[float, float] | None = None,
        **kwargs,
    ) -> plt.Figure:
        """
        Cria um diagrama de Hovmöller a partir de dados diários.
        """
        if not hasattr(self, "processor") or self.processor is None:
            raise AttributeError(
                "ZCITPlotter precisa ser inicializado com uma instância de DataProcessor para esta função."
            )

        import matplotlib.dates as mdates

        # 1. Preparar os dados
        hov_data = self.processor.create_hovmoller_data_daily(daily_data, longitude)

        # 2. Criar a figura
        fig, ax = plt.subplots(figsize=figsize)
        resolved_cmap = ZCITColormap.get_colormap(cmap)

        # --- INÍCIO DA CORREÇÃO ---
        # 3. Converter as datas cftime para o formato numérico do Matplotlib
        #    Isso é necessário para a função contourf
        time_as_nums = mdates.date2num(hov_data.time.values)
        # --- FIM DA CORREÇÃO ---

        # 4. Plotar os dados (contourf) usando as datas numéricas
        im = ax.contourf(
            time_as_nums,  # <--- MUDANÇA AQUI
            hov_data.lat.values,
            hov_data.T,
            levels=np.arange(180, 301, 5),
            cmap=resolved_cmap,
            extend="both",
        )

        # 5. Configurar elementos do gráfico
        cbar = plt.colorbar(im, ax=ax, orientation="vertical", pad=0.02)
        cbar.set_label("OLR (W/m²)", fontsize=12)
        ax.set_xlabel("Data", fontsize=12)
        ax.set_ylabel("Latitude", fontsize=12)
        ax.set_title(
            f"Diagrama de Hovmöller (Diário) - Longitude {hov_data.lon.item():.1f}°W",
            fontsize=14,
            fontweight="bold",
        )
        ax.grid(True, alpha=0.3, linestyle="--")

        # 6. Configurar eixos
        if ylims:
            ax.set_ylim(ylims)

        ax.yaxis.set_major_locator(plt.MultipleLocator(y_tick_interval))
        # O formatador de datas do Matplotlib funciona perfeitamente com seu formato numérico interno
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=x_tick_interval_days))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

        plt.tight_layout()
        self.figures.append(fig)
        return fig

    def plot_annual_cycle(
        self,
        olr_data: xr.Dataset,
        year: int,
        pentadas: list[int] | None = None,
        output_dir: str | Path | None = None,
        create_animation: bool = False,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Cria visualizações para ciclo anual.

        Parameters
        ----------
        olr_data : xr.Dataset
            Dados OLR anuais
        year : int
            Ano
        pentadas : list, optional
            Pentadas específicas (None = todas)
        output_dir : str or Path, optional
            Diretório de saída
        create_animation : bool
            Se cria animação
        **kwargs
            Parâmetros adicionais

        Returns
        -------
        dict
            Resultados do processamento
        """
        if pentadas is None:
            pentadas = list(range(1, 74))  # Todas as pentadas

        results = {
            "year": year,
            "pentadas_processed": [],
            "output_files": [],
            "animation_file": None,
        }

        # Criar diretório se necessário
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        # Processar cada pentada
        for pentada in pentadas:
            try:
                # Gerar nome do arquivo
                if output_dir:
                    filename = output_dir / f"zcit_{year}_p{pentada:02d}.png"
                else:
                    filename = None

                # Criar visualização
                pent_results = self.plot_pentada(
                    olr_data, pentada, year, save_path=filename, **kwargs
                )

                results["pentadas_processed"].append(pentada)
                if filename:
                    results["output_files"].append(filename)

                # Fechar figura para economizar memória
                plt.close(pent_results["figure"])

            except Exception as e:
                logger.error(f"Erro ao processar pentada {pentada}: {e}")

        # Criar animação se solicitado
        if create_animation and output_dir and results["output_files"]:
            try:
                anim_file = self._create_animation(
                    results["output_files"],
                    output_dir / f"zcit_{year}_animation.gif",
                )
                results["animation_file"] = anim_file
            except Exception as e:
                logger.error(f"Erro ao criar animação: {e}")

        return results

    def plot_comparison(
        self,
        datasets: dict[str, xr.Dataset],
        pentada: int,
        labels: dict[str, str] | None = None,
        layout: str = "grid",
        figsize: tuple[float, float] | None = None,
        save_path: str | None = None,
        **kwargs,
    ) -> plt.Figure:
        """
        Cria visualização comparativa.

        Parameters
        ----------
        datasets : dict
            Dicionário {nome: dataset}
        pentada : int
            Pentada para comparar
        labels : dict, optional
            Labels customizados
        layout : str
            Layout ('grid', 'horizontal', 'vertical')
        figsize : tuple, optional
            Tamanho da figura
        save_path : str, optional
            Caminho para salvar
        **kwargs
            Parâmetros adicionais

        Returns
        -------
        matplotlib.figure.Figure
            Figura criada
        """
        n_plots = len(datasets)

        # Determinar layout
        if layout == "grid":
            cols = int(np.ceil(np.sqrt(n_plots)))
            rows = int(np.ceil(n_plots / cols))
        elif layout == "horizontal":
            rows, cols = 1, n_plots
        else:  # vertical
            rows, cols = n_plots, 1

        # Tamanho da figura
        if figsize is None:
            figsize = (6 * cols, 5 * rows)

        # Criar figura
        fig = plt.figure(figsize=figsize)

        # Criar subplots
        for i, (name, data) in enumerate(datasets.items()):
            ax = fig.add_subplot(rows, cols, i + 1, projection=ccrs.PlateCarree())

            # Criar visualizador temporário
            viz = ZCITVisualizer()
            viz.fig = fig
            viz.ax = ax

            # Plotar
            viz.plot_olr_field(data, pentada)
            viz.add_geographic_features()
            viz.setup_gridlines()

            # Título
            label = labels.get(name, name) if labels else name
            ax.set_title(f"{label} - Pentada {pentada}", fontsize=14)

        plt.tight_layout()

        # Salvar
        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches="tight")

        self.figures.append(fig)
        return fig

    def plot_hovmoller(
        self,
        pentad_data: xr.Dataset,
        longitude: float,
        cmap: str = "classic",
        figsize: tuple[float, float] = (12, 8),
        save_path: str | None = None,
        x_tick_interval: int = 10,
        y_tick_interval: int = 20,
        ylims: tuple[float, float] | None = None,
        **kwargs,
    ) -> plt.Figure:
        """
        Cria diagrama de Hovmöller com eixos customizáveis.

        Parameters
        ----------
        # ... (parâmetros existentes) ...
        y_tick_interval : int
            Intervalo para os ticks no eixo Y (latitude).
        ylims : tuple, optional
            Limites para o eixo Y (latitude), e.g., (-30, 30).
        """
        # ... (código para obter hov_data, criar fig, ax, e contourf) ...
        if self.processor:
            hov_data = self.processor.create_hovmoller_data(pentad_data, longitude)
        else:
            hov_data = pentad_data["olr"].sel(lon=longitude, method="nearest")

        fig, ax = plt.subplots(figsize=figsize)

        resolved_cmap = ZCITColormap.get_colormap(cmap)

        im = ax.contourf(
            hov_data.pentada,
            hov_data.lat,
            hov_data.T,
            levels=20,
            cmap=resolved_cmap,
            extend="both",
        )

        cbar = plt.colorbar(im, ax=ax, orientation="vertical", pad=0.02)
        cbar.set_label("OLR [W/m²]", fontsize=12)

        ax.set_xlabel("Pêntada", fontsize=12)
        ax.set_ylabel("Latitude", fontsize=12)
        ax.set_title(f"Diagrama de Hovmöller - Longitude {longitude:.1f}°", fontsize=14)
        ax.grid(True, alpha=0.3)

        # --- BLOCO DE CÓDIGO ATUALIZADO ---
        # Configurar os ticks e limites dos eixos X e Y

        # Eixo X (Pêntadas)
        ax.set_xticks(np.arange(1, 74, x_tick_interval))

        # Eixo Y (Latitude)
        # Define os limites do eixo Y se forem fornecidos
        if ylims:
            ax.set_ylim(ylims)
            y_min, y_max = ylims
        else:
            y_min, y_max = -90, 90

        # Define os ticks do eixo Y com base nos limites
        ax.set_yticks(np.arange(y_min, y_max + 1, y_tick_interval))

        ax.tick_params(axis="both", labelsize=10)
        # --- FIM DO BLOCO ATUALIZADO ---

        if save_path:
            fig.savefig(save_path, dpi=150, bbox_inches="tight")

        self.figures.append(fig)
        return fig

    def _create_animation(
        self,
        image_files: list[Path],
        output_file: Path,
        fps: int = 2,
        duration: int = 500,
    ) -> Path:
        """Cria animação a partir de imagens."""
        try:
            import imageio

            images = []
            for filename in image_files:
                images.append(imageio.imread(filename))

            imageio.mimsave(output_file, images, fps=fps, duration=duration)
            logger.info(f"Animação criada: {output_file}")

            return output_file

        except ImportError:
            logger.error("imageio não instalado. Instale com: pip install imageio")
            raise

    def close_all(self):
        """Fecha todas as figuras criadas."""
        for fig in self.figures:
            plt.close(fig)
        self.figures.clear()


def plot_zcit_quick(
    olr_data: xr.Dataset,
    pentada: int,
    year: int,
    template: str = "publication",
    save_path: str | None = None,
    **kwargs,
) -> tuple[plt.Figure, dict[str, Any]]:
    """
    Função de conveniência para criar visualização ZCIT rapidamente.

    Parameters
    ----------
    olr_data : xr.Dataset
        Dados OLR
    pentada : int
        Número da pentada
    year : int
        Ano
    template : str
        Template de visualização
    save_path : str, optional
        Caminho para salvar
    **kwargs
        Parâmetros adicionais

    Returns
    -------
    fig : matplotlib.figure.Figure
        Figura criada
    results : dict
        Resultados da análise

    Example
    -------
    >>> fig, results = plot_zcit_quick(olr_data, pentada=30, year=2024,
    ...                                save_path='zcit_p30_2024.png')
    """
    # Criar processador se disponível
    processor = None
    if LOCZCIT_AVAILABLE:
        try:
            processor = DataProcessor()
        except Exception:
            pass

    # Criar plotter
    plotter = ZCITPlotter(processor, default_template=template)

    # Criar visualização
    results = plotter.plot_pentada(
        olr_data, pentada, year, save_path=save_path, **kwargs
    )

    return results["figure"], results


def create_publication_figure(
    olr_data: xr.Dataset,
    pentada: int,
    year: int,
    title: str | None = None,
    save_path: str | None = None,
    dpi: int = 300,
) -> plt.Figure:
    """
    Cria figura pronta para publicação com configurações otimizadas.

    Parameters
    ----------
    olr_data : xr.Dataset
        Dados OLR
    pentada : int
        Número da pentada
    year : int
        Ano
    title : str, optional
        Título customizado
    save_path : str, optional
        Caminho para salvar
    dpi : int
        Resolução

    Returns
    -------
    matplotlib.figure.Figure
        Figura criada
    """
    viz = ZCITVisualizer(template="publication")
    fig, ax = viz.quick_plot(
        olr_data,
        pentada,
        title=title or f"ZCIT Analysis - Pentad {pentada}, {year}",
        save_path=save_path,
    )

    # Ajustes finais para publicação
    plt.tight_layout()

    return fig


# Exportar TEMPLATES para acesso externo
TEMPLATES = ZCITVisualizer.TEMPLATES


# Função de diagnóstico do módulo
def check_plotting_dependencies(verbose: bool = True) -> dict:
    """
    Verifica o status das dependências do módulo plotting.

    Parameters
    ----------
    verbose : bool
        Se True, imprime relatório detalhado

    Returns
    -------
    dict
        Status de cada dependência
    """
    import importlib

    dependencies = {
        "core": {
            "matplotlib": "matplotlib",
            "cartopy": "cartopy",
            "numpy": "numpy",
            "xarray": "xarray",
            "pandas": "pandas",
            "shapely": "shapely",
        },
        "optional": {
            "geopandas": "geopandas",
            "scipy": "scipy",
            "pillow": "PIL",
            "imageio": "imageio",
        },
    }

    status = {}

    for category, deps in dependencies.items():
        status[category] = {}
        for name, module in deps.items():
            try:
                mod = importlib.import_module(module)
                version = getattr(mod, "__version__", "unknown")
                status[category][name] = {
                    "installed": True,
                    "version": version,
                }
            except ImportError:
                status[category][name] = {"installed": False, "version": None}

    if verbose:
        print("=== LOCZCIT Plotting Dependencies Status ===\n")

        for category, deps in status.items():
            print(f"{category.upper()} Dependencies:")
            for name, info in deps.items():
                icon = "✓" if info["installed"] else "✗"
                version = f"v{info['version']}" if info["version"] else "not installed"
                print(f"  {icon} {name:<15} {version}")
            print()

        # Recomendações
        missing_core = [
            name for name, info in status["core"].items() if not info["installed"]
        ]
        if missing_core:
            print("⚠️  ATENÇÃO: Dependências essenciais faltando!")
            print(f"   Instale com: pip install {' '.join(missing_core)}")

    return status


def plot_complete_zcit_analysis(
    media_global: xr.DataArray,
    dados_study_area: xr.DataArray | None = None,
    coords_validos: list[tuple[float, float]] | None = None,
    coords_outliers: list[tuple[float, float]] | None = None,
    sistemas_convectivos: list[tuple[float, float]] | None = None,
    zcit_line: LineString | None = None,
    study_area: tuple[float, float, float, float]
    | str
    | Path
    | gpd.GeoDataFrame
    | None = None,
    titulo: str | None = None,
    template: str = "publication",
    xlims: tuple[float, float] = (-80, 0),
    ylims: tuple[float, float] = (-12, 17),
    colormap: str = "classic",
    credits: str = "NOAA",  # "NOAA" ou "ERA5"
    save_path: str | None = None,
    **kwargs,
) -> tuple[plt.Figure, plt.Axes]:
    """
    Cria visualização completa da análise ZCIT com lógica unificada de área de estudo.

    ANALOGIA DO DETETIVE ESPECIALISTA 🕵️
    É como um detetive que pode trabalhar com diferentes tipos de evidências:
    1. 🗺️ Coordenadas simples (lat_min, lat_max, lon_min, lon_max)
    2. 📁 Arquivos de geometria (.shp, .geojson, .parquet)
    3. 🧩 GeoDataFrame já carregado
    4. 🎯 Área padrão da biblioteca (se None)

    Parameters
    ----------
    media_global : xr.DataArray
        Campo de OLR médio global para plotar como fundo
    dados_study_area : xr.DataArray, optional
        Dados da área de estudo (para análises específicas)
    coords_validos : list of tuples, optional
        Lista de coordenadas válidas da ZCIT [(lon, lat), ...]
    coords_outliers : list of tuples, optional
        Lista de coordenadas outliers [(lon, lat), ...]
    sistemas_convectivos : list of tuples, optional
        Lista de sistemas convectivos isolados [(lon, lat), ...]
    zcit_line : LineString, optional
        Linha interpolada da ZCIT
    study_area : tuple, str, Path, or GeoDataFrame, optional
        Área de estudo em diferentes formatos:
        - tuple: (lat_min, lat_max, lon_min, lon_max) para bounding box
        - str/Path: Caminho para arquivo (.shp, .geojson, .parquet)
        - GeoDataFrame: Objeto já carregado
        - None: Usa área padrão da biblioteca
    data_inicio : str
        Data de início para título (formato 'YYYY-MM-DD')
    template : str
        Template de visualização ('publication', 'presentation', 'web', 'report')
    xlims : tuple
        Limites do eixo X (longitude)
    ylims : tuple
        Limites do eixo Y (latitude)
    colormap : str
        Nome do colormap a usar
    credits : str, default "NOAA"
        Fonte de dados para os créditos: "NOAA", "ERA5" ou texto customizado
    save_path : str, optional
        Caminho para salvar a figura
    **kwargs
        Argumentos adicionais

    Returns
    -------
    fig : matplotlib.figure.Figure
        Figura criada
    ax : matplotlib.axes.Axes
        Eixos da figura

    Examples
    --------
    >>> # Uso com coordenadas simples
    >>> fig, ax = plot_complete_zcit_analysis(
    ...     media_global=media_global,
    ...     coords_validos=coords_validos,
    ...     study_area=(-5, 5, -37, -10),  # bbox
    ...     data_inicio="2024-03-01"
    ... )

    >>> # Uso com arquivo shapefile
    >>> fig, ax = plot_complete_zcit_analysis(
    ...     media_global=media_global,
    ...     coords_validos=coords_validos,
    ...     study_area="/path/to/area.shp",
    ...     data_inicio="2024-03-01"
    ... )

    >>> # Uso com área padrão
    >>> fig, ax = plot_complete_zcit_analysis(
    ...     media_global=media_global,
    ...     coords_validos=coords_validos,
    ...     study_area=None,  # Usa área padrão
    ...     data_inicio="2024-03-01"
    ... )
    """

    # ========================================================================
    # ETAPA 1: CONFIGURAÇÃO INICIAL
    # ========================================================================

    # Meses em português para título

    print("\n🎨 ETAPA 4: Criando visualização com contexto global...")
    print("=" * 60)
    print("🎨 GERANDO VISUALIZAÇÃO FINAL...")

    # ========================================================================
    # ETAPA 2: INICIALIZAÇÃO DO VISUALIZADOR
    # ========================================================================

    # Inicializar o visualizador com template
    viz = ZCITVisualizer(template=template)
    viz.create_figure(figsize=(12, 5))

    # Configurar limites do mapa
    viz.setup_gridlines(xlims=xlims, ylims=ylims, x_interval=1, y_interval=1)

    # Obter colormap personalizado
    # cmap_classic = ZCITColormap.get_colormap(name=colormap)

    # ========================================================================
    # ETAPA 3: PLOTAR CAMPO DE OLR
    # ========================================================================

    # Configuração da barra de cores
    config_barra_cores = {
        "position": [
            0.15,
            0.03,
            0.7,
            0.03,
        ]  # [esquerda, fundo, largura, altura]
    }

    # Plotar o campo de OLR
    viz.plot_olr_field(
        data=media_global,
        pentada=None,  # Não usar pentada
        cbar_config=config_barra_cores,
    )

    # ========================================================================
    # ETAPA 4: ADICIONAR FEATURES GEOGRÁFICAS
    # ========================================================================

    viz.add_geographic_features()

    # ========================================================================
    # ETAPA 5: PLOTAR COORDENADAS ZCIT
    # ========================================================================

    # Sistemas convectivos isolados (opcional)
    if sistemas_convectivos:
        viz.plot_zcit_coordinates(
            sistemas_convectivos,
            color="yellow",
            marker="*",
            s=300,  # Tamanho maior
            edge_color="black",
            edge_width=0.3,
            label="Sistemas Isolados",
        )

    # Pontos válidos (usados na interpolação)
    if coords_validos:
        viz.plot_zcit_coordinates(
            coords_validos, color="green", marker="o", label="ZCIT Válida"
        )

    # Outliers
    if coords_outliers:
        viz.plot_zcit_coordinates(
            coords_outliers,
            color="red",
            marker="x",
            s=50,  # Tamanho maior para destacar
            label="Outliers",
        )

    # ========================================================================
    # ETAPA 6: PLOTAR LINHA INTERPOLADA
    # ========================================================================

    if zcit_line:
        viz.plot_zcit_lines(
            zcit_line=zcit_line,
            std_value=2,
            colors={"mean": "green", "plus_std": "red", "minus_std": "blue"},
            labels={
                "mean": "Posição Média da ZCIT",
                "plus_std": "Limite Superior (+2°)",
                "minus_std": "Limite Inferior (-2°)",
            },
        )

    # ========================================================================
    # ETAPA 7: PROCESSAR E PLOTAR ÁREA DE ESTUDO (LÓGICA UNIFICADA)
    # ========================================================================

    def _plot_study_area_unified(viz, study_area):
        """
        Função interna que implementa a lógica unificada de área de estudo.

        ANALOGIA DO TRADUTOR UNIVERSAL 🌍
        É como um tradutor que consegue entender diferentes "idiomas" de geometria:
        - Idioma "coordenadas" (tupla de números)
        - Idioma "arquivo" (caminho para shapefile/geojson/parquet)
        - Idioma "objeto" (GeoDataFrame já carregado)
        - Idioma "padrão" (área da biblioteca)
        """

        # Determinar o tipo de study_area e processar adequadamente
        if study_area is None:
            # Caso 1: Usar área padrão da biblioteca
            print("📍 Usando área padrão da biblioteca...")
            default_shapefile_path = (
                Path(__file__).resolve().parent.parent.parent
                / "data"
                / "shapefiles"
                / "Area_LOCZCIT.parquet"
            )

            if default_shapefile_path.exists():
                try:
                    viz.plot_study_area(
                        default_shapefile_path,
                        edgecolor="orange",
                        linestyle="--",
                        linewidth=1.5,
                        label="Área de Busca",
                    )
                    print(f"✅ Área padrão carregada: {default_shapefile_path}")
                except Exception as e:
                    print(f"⚠️ Erro ao carregar área padrão: {e}")
            else:
                print("⚠️ Área padrão não encontrada")

        elif isinstance(study_area, tuple) and len(study_area) == 4:
            # Caso 2: Coordenadas bounding box (lat_min, lat_max, lon_min, lon_max)
            print("📍 Usando coordenadas bounding box...")
            lat_min, lat_max, lon_min, lon_max = study_area

            # Criar um retângulo a partir das coordenadas
            import geopandas as gpd
            from shapely.geometry import box

            # Criar geometria box
            bbox_geom = box(lon_min, lat_min, lon_max, lat_max)

            # Criar GeoDataFrame temporário
            gdf_bbox = gpd.GeoDataFrame([1], geometry=[bbox_geom], crs="EPSG:4326")

            viz.plot_study_area(
                gdf_bbox,
                edgecolor="orange",
                linestyle="--",
                linewidth=1.5,
                label="Área de Busca",
            )
            print(f"✅ Bounding box plotado: {study_area}")

        elif isinstance(study_area, (str, Path)):
            # Caso 3: Caminho para arquivo
            print(f"📍 Carregando arquivo: {study_area}")
            try:
                viz.plot_study_area(
                    study_area,
                    edgecolor="orange",
                    linestyle="--",
                    linewidth=1.5,
                    label="Área de Busca",
                )
                print(f"✅ Arquivo carregado: {study_area}")
            except Exception as e:
                print(f"❌ Erro ao carregar arquivo: {e}")

        elif hasattr(study_area, "geometry"):
            # Caso 4: GeoDataFrame já carregado
            print("📍 Usando GeoDataFrame fornecido...")
            try:
                viz.plot_study_area(
                    study_area,
                    edgecolor="orange",
                    linestyle="--",
                    linewidth=1.5,
                    label="Área de Busca",
                )
                print("✅ GeoDataFrame plotado")
            except Exception as e:
                print(f"❌ Erro ao plotar GeoDataFrame: {e}")
        else:
            print(f"⚠️ Tipo de study_area não reconhecido: {type(study_area)}")

    # Executar a lógica unificada
    _plot_study_area_unified(viz, study_area)

    # ========================================================================
    # ETAPA 8: CONFIGURAR TÍTULO E ELEMENTOS FINAIS
    # ========================================================================

    # Configurar título
    if titulo:
        viz.ax.set_title(titulo.capitalize(), fontsize=16, fontweight="bold")
    else:
        titulo = "Análise da Posição da Zona de Convergência Intertropical (ZCIT)"
        print(f"📌 Título padrão: {titulo}")
        viz.ax.set_title(titulo.capitalize(), fontsize=16, fontweight="bold")

    # ========================================================================
    # ETAPA 9: ADICIONAR ELEMENTOS INFORMATIVOS
    # ========================================================================

    # Legenda
    viz.add_legend(loc="upper left", title="Legenda", fontsize=9, framealpha=1, ncol=1)

    # Barra de escala
    viz.add_scale_bar(
        units="km",
        location="lower left",
        # loc_geo=(-76.8, -10.5),
        length_fraction=0.08,  # 8% do tamanho da figura
        scale_loc="bottom",
        rotation="horizontal-only",
        zorder=20,
    )

    # Créditos
    viz.add_credits(source=credits)

    # Logo
    viz.add_logo(
        position="upper right",  #'upper right', 'upper left', 'lower left', 'lower right', 'right', 'center left', 'center right', 'lower center', 'upper center', 'center'
        # loc_geo=(-5, 9),
        zoom=0.07,  # 7% do tamanho original(Ajuste o zoom conforme necessário)
        alpha=1,
        margin=(
            0.18,
            0.002,
            0.0,
            0.0,
        ),  # margem de 18% no topo e margem de 1% a direita, e 0% esquerda e inferior
    )

    # Rosa dos ventos
    viz.add_north_arrow(
        position="upper right",  # 'upper right', 'upper left', 'lower left', 'lower right', 'right', 'center left', 'center right', 'lower center', 'upper center', 'center'
        # loc_geo=(-5, 15),
        zoom=0.1,  # 10% do tamanho original
        alpha=1,
        margin=(
            0.02,
            0.03,
            0.0,
            0.0,
        ),  # margem de 2% no topo e margem de 3% a direita, e 0% esquerda e inferior
        zorder=12,
    )

    # ========================================================================
    # ETAPA 10: FINALIZAÇÃO
    # ========================================================================

    # Salvar se solicitado
    if save_path:
        try:
            viz.save(save_path)
            print(f"💾 Figura salva em: {save_path}")
        except Exception as e:
            print(f"❌ Erro ao salvar: {e}")

    print("✅ Visualização pronta. Exibindo...")

    return viz.fig, viz.ax


# ============================================================================
# FUNÇÃO DE CONVENIÊNCIA PARA CASOS SIMPLES
# ============================================================================


def plot_zcit_quick_analysis(
    media_global: xr.DataArray,
    coords_validos: list[tuple[float, float]],
    data_inicio: str = "2024-03-01",
    study_area: tuple[float, float, float, float]
    | str
    | Path
    | gpd.GeoDataFrame
    | None = None,
    save_path: str | None = None,
) -> tuple[plt.Figure, plt.Axes]:
    """
    Função simplificada para análise rápida da ZCIT.

    ANALOGIA DO ASSISTENTE EFICIENTE 🚀
    É como um assistente que pega os elementos essenciais
    e cria rapidamente uma visualização limpa e profissional.

    Parameters
    ----------
    media_global : xr.DataArray
        Campo OLR médio
    coords_validos : list
        Coordenadas válidas da ZCIT
    data_inicio : str
        Data para título
    study_area : various, optional
        Área de estudo (same logic as main function)
    save_path : str, optional
        Caminho para salvar

    Returns
    -------
    fig, ax : matplotlib objects
    """
    return plot_complete_zcit_analysis(
        media_global=media_global,
        coords_validos=coords_validos,
        data_inicio=data_inicio,
        study_area=study_area,
        save_path=save_path,
        template="publication",
        figsize=(12, 8),
    )


# ============================================================================
# FUNÇÃO DE DEMONSTRAÇÃO/TESTE
# ============================================================================


def demo_study_area_types():
    """
    Demonstra os diferentes tipos de study_area suportados.

    ANALOGIA DO CATÁLOGO DE PRODUTOS 📖
    É como um catálogo que mostra todos os "sabores" disponíveis
    de área de estudo que a função pode processar.
    """

    print("🌍 DEMONSTRAÇÃO: Tipos de study_area suportados")
    print("=" * 60)

    examples = [
        {
            "tipo": "Área Padrão",
            "codigo": "study_area=None",
            "descricao": "Usa área padrão da biblioteca (Area_LOCZCIT.parquet)",
        },
        {
            "tipo": "Coordenadas (Bounding Box)",
            "codigo": "study_area=(-5, 5, -37, -10)",
            "descricao": "Retângulo definido por (lat_min, lat_max, lon_min, lon_max)",
        },
        {
            "tipo": "Arquivo Shapefile",
            "codigo": 'study_area="/path/to/area.shp"',
            "descricao": "Carrega geometria de arquivo shapefile",
        },
        {
            "tipo": "Arquivo GeoJSON",
            "codigo": 'study_area="/path/to/area.geojson"',
            "descricao": "Carrega geometria de arquivo GeoJSON",
        },
        {
            "tipo": "Arquivo GeoParquet",
            "codigo": 'study_area="/path/to/area.parquet"',
            "descricao": "Carrega geometria de arquivo Parquet geoespacial",
        },
        {
            "tipo": "GeoDataFrame",
            "codigo": "study_area=gdf",
            "descricao": "Usa GeoDataFrame já carregado em memória",
        },
    ]

    for i, ex in enumerate(examples, 1):
        print(f"{i}. {ex['tipo']}")
        print(f"   Código: {ex['codigo']}")
        print(f"   Descrição: {ex['descricao']}")
        print()

    print("💡 DICA: A função detecta automaticamente o tipo e processa adequadamente!")


# Converte a data de início e pega o número do mês e o ano
# data_obj = datetime.strptime(data_inicio, '%Y-%m-%d')
# nome_do_mes = meses_em_portugues[data_obj.month]
# ano = data_obj.year


# Criar def para captura mes e ano
def get_month_and_year(data_inicio: str) -> tuple[str, int]:
    """
    Captura o mês e o ano a partir da data de início.

    Parameters
    ----------
    data_inicio : str
        Data no formato 'YYYY-MM-DD'

    Returns
    -------
    tuple
        (nome_do_mes, ano)
    """
    from datetime import datetime

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

    data_obj = datetime.strptime(data_inicio, "%Y-%m-%d")
    nome_do_mes = meses_em_portugues[data_obj.month]
    ano = data_obj.year

    return nome_do_mes, ano


# Demonstração de uso
if __name__ == "__main__":
    print("Módulo de visualização LOCZCIT-IQR (Versão Aprimorada)")
    print("\nRecursos disponíveis:")
    print("- ZCITVisualizer: Classe principal com templates predefinidos")
    print("- ZCITPlotter: Interface de alto nível para visualizações complexas")
    print("- plot_zcit_quick(): Função rápida para visualizações simples")
    print("- create_publication_figure(): Figuras prontas para publicação")
    print("\nTemplates disponíveis: publication, presentation, web, report")
    print("\nExemplo de uso:")
    print(">>> viz = ZCITVisualizer(template='publication')")
    print(">>> fig, ax = viz.quick_plot(olr_data, pentada=30)")
    print("Função de Visualização ZCIT com Lógica Unificada de Study Area")
    print("=" * 65)
    demo_study_area_types()
