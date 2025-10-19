"""
loczcit_iqr/core/processor.py
============================

Módulo principal para processamento de dados OLR (Outgoing Longwave Radiation)
e identificação da Zona de Convergência Intertropical (ZCIT).

Este módulo é como uma "fábrica de processamento de dados climáticos", onde:
- Os dados brutos de OLR são a "matéria-prima"
- As pentadas são os "produtos intermediários" (agregações de 5-6 [Se ano for bissexto] dias)
- A identificação da ZCIT é o "produto final"

Author: LOCZCIT-IQR Development Elivaldo Rocha
License: MIT
"""

from __future__ import annotations

import logging
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    import cftime
    import geopandas as gpd
    import regionmask as rm

import dask.array as da
import numpy as np
import pandas as pd
import xarray as xr
from scipy import stats
from tqdm import tqdm

try:
    import cftime

    HAS_CFTIME = True
except ImportError:
    HAS_CFTIME = False

try:
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False
    print("AVISO: A biblioteca `pyarrow` não está instalada.")

try:
    import geopandas as gpd

    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    print("AVISO: A biblioteca `geopandas` não está instalada.")

try:
    import regionmask as rm

    HAS_REGIONMASK = True
except ImportError:
    HAS_REGIONMASK = False
    print("AVISO: A biblioteca `regionmask` não está instalada.")


# Importações da biblioteca LOCZCIT
from loczcit_iqr.utils import (
    date_to_pentada,
    pentada_to_dates,
    validate_coordinates,
    validate_date,
    validate_olr_values,
)

# Configuração do logger
logger = logging.getLogger(__name__)

# Type aliases para melhor legibilidade
Coordinate = tuple[float, float]  # (longitude, latitude)
DateLike = Union[datetime, "cftime.datetime", np.datetime64]
PathLike = Union[str, Path]
MaskSource = Union[PathLike, "gpd.GeoDataFrame", xr.DataArray]


class DataProcessor:
    """
    Processador de dados OLR para análise da ZCIT.

    Esta classe é como um "chef de cozinha" que:
    1. Prepara os ingredientes (dados OLR diários)
    2. Cozinha em porções adequadas (cria pentadas)
    3. Tempera e finaliza (aplica máscaras, encontra mínimos)
    4. Serve o prato pronto (dados processados para análise)

    Attributes
    ----------
    use_dask : bool
        Se True, usa processamento paralelo com Dask para grandes volumes
    n_workers : int
        Número de workers para processamento paralelo
    chunk_size : Dict[str, int]
        Tamanhos de chunk para processamento com Dask
    default_study_area_path : Optional[Path]
        Caminho para o arquivo padrão da área de estudo da ZCIT

    Examples
    --------
    >>> processor = DataProcessor(use_dask=True, n_workers=4)
    >>> pentads = processor.create_pentads(olr_data, year=2024)
    >>> min_coords = processor.find_minimum_coordinates(pentads['olr'])
    """

    DEFAULT_STUDY_AREA_FILENAME = "Area_LOCZCIT.parquet"
    DEFAULT_CHUNK_SIZE = {"time": 30, "lat": 50, "lon": 50}
    DEFAULT_CACHE_SIZE = 5

    def __init__(
        self,
        chunk_size: dict[str, int] | None = None,
        use_dask: bool = True,
        n_workers: int = 4,
        log_level: int | str = logging.INFO,
    ) -> None:
        """
        Inicializa o processador de dados.

        Parameters
        ----------
        chunk_size : Dict[str, int], optional
            Tamanhos de chunk para processamento com Dask
        use_dask : bool, default True
            Se True, usa processamento paralelo com Dask
        n_workers : int, default 4
            Número de workers para processamento paralelo
        log_level : int or str, default logging.INFO
            Nível de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.use_dask = use_dask
        self.n_workers = n_workers
        self.chunk_size = chunk_size or self.DEFAULT_CHUNK_SIZE.copy()

        # Cache para pentadas processadas
        self._pentads_cache: dict[str, xr.Dataset] = {}
        self._pentads_cache_size = self.DEFAULT_CACHE_SIZE

        # Configuração do logging
        self._setup_logging(log_level)

        # Verificação de dependências opcionais
        self._check_optional_dependencies()

        # Configuração do caminho padrão da área de estudo
        self.default_study_area_path: Path | None = None
        self._resolve_default_study_area_path()

    def _setup_logging(self, level: int | str) -> None:
        """
        Configura o sistema de logging.

        Como um "sistema de comunicação" da fábrica, registra todas as
        operações importantes para rastreamento e debugging.
        """
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(level)

    def _check_optional_dependencies(self) -> None:
        """Verifica e alerta sobre dependências opcionais não instaladas."""
        if not HAS_REGIONMASK:
            logger.warning(
                "`regionmask` não instalado. Máscaras geográficas usarão "
                "método alternativo (mais lento)."
            )
        if not HAS_GEOPANDAS:
            logger.warning(
                "`geopandas` não instalado. Funcionalidades de máscara "
                "geográfica podem ser limitadas."
            )
        if not HAS_CFTIME:
            logger.warning(
                "`cftime` não instalado. Suporte a calendários não-padrão "
                "pode ser limitado."
            )

    def _resolve_default_study_area_path(self) -> None:
        """
        Localiza o arquivo padrão da área de estudo.

        Como um "GPS" que encontra automaticamente o "mapa" da região
        de interesse (área típica da ZCIT).
        """
        try:
            current_file = Path(__file__).resolve()
            package_dir = current_file.parent.parent.parent

            candidate_path = (
                package_dir / "data" / "shapefiles" / self.DEFAULT_STUDY_AREA_FILENAME
            )

            if candidate_path.exists() and candidate_path.is_file():
                self.default_study_area_path = candidate_path
                logger.info(
                    f"Arquivo padrão da área de estudo encontrado: "
                    f"{self.default_study_area_path}"
                )
            else:
                logger.warning(
                    f"Arquivo padrão da área de estudo "
                    f"'{self.DEFAULT_STUDY_AREA_FILENAME}' não encontrado em "
                    f"{candidate_path}. Funcionalidades de área padrão podem "
                    f"não funcionar."
                )
        except Exception as e:
            logger.error(f"Erro ao localizar arquivo padrão da área de estudo: {e}")

    def _manage_pentads_cache(
        self, key: str, value: xr.Dataset | None = None
    ) -> xr.Dataset | None:
        """
        Gerencia o cache de pentadas processadas.

        Como uma "despensa" que armazena produtos processados recentemente
        para reutilização rápida, economizando tempo de processamento.

        Parameters
        ----------
        key : str
            Chave única para identificar o conjunto de pentadas
        value : xr.Dataset, optional
            Se fornecido, armazena no cache. Se None, recupera do cache.

        Returns
        -------
        xr.Dataset or None
            Dataset recuperado do cache ou None se não encontrado
        """
        if value is None:  # Modo de recuperação
            return self._pentads_cache.get(key)

        # Modo de armazenamento
        if len(self._pentads_cache) >= self._pentads_cache_size:
            # Remove o item mais antigo (FIFO)
            oldest_key = next(iter(self._pentads_cache))
            del self._pentads_cache[oldest_key]
            logger.debug(f"Cache cheio. Removido item: {oldest_key}")

        self._pentads_cache[key] = value
        logger.debug(f"Pentada {key} armazenada no cache")
        return value

    @staticmethod
    def _is_leap_year(year: int) -> bool:
        """
        Verifica se um ano é bissexto.

        Como verificar se fevereiro tem um "dia extra" no calendário.
        """
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    def _remove_leap_days(self, data: xr.Dataset) -> xr.Dataset:
        """
        Remove dias 29 de fevereiro do dataset.

        Como remover as "exceções" do calendário para manter a
        consistência anual de 365 dias.
        """
        if "time" not in data.coords:
            logger.warning(
                "Coordenada 'time' não encontrada. "
                "Não é possível remover dias bissextos."
            )
            return data

        time_values = data.time.values
        if not time_values.size:
            return data

        # Criar máscara para manter apenas dias não-bissextos
        keep_mask = np.ones(len(time_values), dtype=bool)

        for i, time_coord in enumerate(time_values):
            if hasattr(time_coord, "year"):
                year, month, day = (
                    time_coord.year,
                    time_coord.month,
                    time_coord.day,
                )
                if month == 2 and day == 29 and self._is_leap_year(year):
                    keep_mask[i] = False

        if not np.all(keep_mask):
            n_removed = np.sum(~keep_mask)
            logger.info(f"Removendo {n_removed} dia(s) 29/02 do dataset")
            return data.isel(time=keep_mask)

        return data

    def create_pentads(
        self,
        olr_data: xr.Dataset,
        year: int,
        remove_leap_days: bool = True,
        method: str = "mean",
        min_days_required: int = 3,
    ) -> xr.Dataset:
        """
        Cria pentadas (agregados de 5-6 dias) a partir de dados diários.

        Como transformar "fotos diárias" em "álbuns semanais" para
        melhor visualização de padrões climáticos.

        Parameters
        ----------
        olr_data : xr.Dataset
            Dados diários de OLR com coordenada 'time'
        year : int
            Ano para processar
        remove_leap_days : bool, default True
            Se True, remove dias 29/02 antes do processamento
        method : str, default "mean"
            Método de agregação: "mean", "median", "min", "max"
        min_days_required : int, default 3
            Número mínimo de dias válidos para calcular uma pentada

        Returns
        -------
        xr.Dataset
            Dataset com pentadas agregadas

        Raises
        ------
        ValueError
            Se ano inválido, método inválido ou dados insuficientes
        """
        # Validação de entrada
        self._validate_pentad_inputs(olr_data, year, method)

        # Verificar cache
        cache_key = self._generate_cache_key(
            olr_data, year, method, remove_leap_days, min_days_required
        )
        cached_result = self._manage_pentads_cache(cache_key)
        if cached_result is not None:
            logger.info(f"Usando pentadas do cache para {year}")
            return cached_result.copy(deep=True)

        logger.info(
            f"Criando pentadas para {year} "
            f"(método: {method}, remover bissextos: {remove_leap_days})"
        )

        try:
            # Selecionar dados do ano
            year_data = self._select_year_data(olr_data, year)

            # Remover dias bissextos se solicitado
            if remove_leap_days:
                year_data = self._remove_leap_days(year_data)

            # Mapear datas para números de pentada
            year_data = self._assign_pentad_numbers(year_data)

            # Aplicar chunks se usando Dask
            if self.use_dask and year_data.nbytes > 100e6:
                year_data = self._apply_dask_chunks(year_data)

            # Agregar por pentada
            pentad_dataset = self._aggregate_by_pentad(
                year_data, year, method, min_days_required
            )

            # Adicionar metadados
            pentad_dataset = self._add_pentad_metadata(
                pentad_dataset,
                year,
                method,
                min_days_required,
                remove_leap_days,
            )

            # Armazenar no cache
            self._manage_pentads_cache(cache_key, pentad_dataset.copy(deep=True))

            logger.info(f"Pentadas para {year} criadas com sucesso")
            return pentad_dataset

        except Exception as e:
            logger.exception(f"Erro ao criar pentadas para {year}")
            raise RuntimeError(f"Falha no processamento de pentadas: {e}") from e

    def _validate_pentad_inputs(
        self, olr_data: xr.Dataset, year: int, method: str
    ) -> None:
        """Valida entradas para criação de pentadas."""
        current_year = datetime.now().year
        if not 1900 <= year <= current_year + 20:
            raise ValueError(
                f"Ano {year} fora da faixa válida (1900-{current_year + 20})"
            )

        valid_methods = ["mean", "median", "min", "max"]
        if method not in valid_methods:
            raise ValueError(f"Método '{method}' inválido. Use um de: {valid_methods}")

        if "time" not in olr_data.coords:
            raise ValueError("Dataset deve ter coordenada 'time'")

        if not olr_data.time.values.size:
            raise ValueError("Coordenada 'time' está vazia")

    def _generate_cache_key(
        self,
        olr_data: xr.Dataset,
        year: int,
        method: str,
        remove_leap_days: bool,
        min_days_required: int,
    ) -> str:
        """Gera chave única para cache de pentadas."""
        # Usa hash dos primeiros valores de tempo para identificar o dataset
        time_hash = pd.util.hash_array(olr_data.time.values[:5].astype(str))

        return (
            f"pentads_y{year}_m{method}_rl{remove_leap_days}_"
            f"mdr{min_days_required}_h{time_hash}"
        )

    def _select_year_data(self, olr_data: xr.Dataset, year: int) -> xr.Dataset:
        """Seleciona dados de um ano específico."""
        time_values = olr_data.time.values

        # Detectar tipo de calendário
        if HAS_CFTIME and isinstance(time_values[0], cftime.datetime):
            calendar = time_values[0].calendar
            start = cftime.datetime(year, 1, 1, 0, 0, 0, calendar=calendar)
            end = cftime.datetime(year, 12, 31, 23, 59, 59, calendar=calendar)
        else:
            start = datetime(year, 1, 1, 0, 0, 0)
            end = datetime(year, 12, 31, 23, 59, 59)

        year_data = olr_data.sel(time=slice(start, end))

        if len(year_data.time) == 0:
            raise ValueError(f"Nenhum dado encontrado para o ano {year}")

        return year_data.copy(deep=True)

    def _assign_pentad_numbers(self, data: xr.Dataset) -> xr.Dataset:
        """Atribui número de pentada a cada data."""
        pentad_numbers = np.empty(len(data.time), dtype=float)

        for i, time_coord in enumerate(data.time.values):
            try:
                # Converter para datetime padrão
                if HAS_CFTIME and isinstance(time_coord, cftime.datetime):
                    dt = datetime(time_coord.year, time_coord.month, time_coord.day)
                elif isinstance(time_coord, np.datetime64):
                    dt = pd.Timestamp(time_coord).to_pydatetime()
                else:
                    dt = time_coord

                pentad_numbers[i] = date_to_pentada(dt, year=dt.year)
            except Exception as e:
                logger.error(f"Erro ao processar data {time_coord}: {e}")
                pentad_numbers[i] = np.nan

        # Adicionar coordenada e remover datas inválidas
        data = data.assign_coords(pentad_number=("time", pentad_numbers))
        data = data.dropna(dim="time", how="any", subset=["pentad_number"])
        data["pentad_number"] = data["pentad_number"].astype(int)

        if len(data.time) == 0:
            raise ValueError("Nenhum dado com pentada válida")

        return data

    def _apply_dask_chunks(self, data: xr.Dataset) -> xr.Dataset:
        """Aplica chunks do Dask se necessário."""
        logger.info("Aplicando chunks do Dask para processamento paralelo")
        data = data.chunk(self.chunk_size)

        # Computar coordenadas se necessário
        if "pentad_number" in data.coords:
            if hasattr(data["pentad_number"].data, "compute"):
                computed_values = data["pentad_number"].data.compute()
                data = data.assign_coords(
                    pentad_number=(data["pentad_number"].dims, computed_values)
                )

        return data

    def _aggregate_by_pentad(
        self,
        data: xr.Dataset,
        year: int,
        method: str,
        min_days_required: int,
    ) -> xr.Dataset:
        """Agrega dados por pentada."""
        pentad_groups = data.groupby("pentad_number")
        aggregated_pentads = []

        # Processar todas as 73 pentadas
        for pentad_num in tqdm(
            range(1, 74),
            desc=f"Processando pentadas {year}",
            unit="pentada",
            disable=not logger.isEnabledFor(logging.DEBUG),
        ):
            if pentad_num in pentad_groups.groups:
                # Agregar dados existentes
                pentad_data = pentad_groups[pentad_num]
                aggregated = self._aggregate_pentad_data(
                    pentad_data, method, min_days_required
                )
            else:
                # Criar pentada vazia
                aggregated = self._create_empty_pentad(data)

            aggregated_pentads.append(aggregated)

        # Concatenar todas as pentadas
        return xr.concat(aggregated_pentads, dim=pd.Index(range(1, 74), name="pentada"))

    def _aggregate_pentad_data(
        self,
        pentad_data: xr.Dataset,
        method: str,
        min_days_required: int,
    ) -> xr.Dataset:
        """Agrega dados de uma pentada específica."""
        # Verificar número mínimo de dias válidos
        if "olr" in pentad_data.data_vars:
            valid_days = (~pentad_data["olr"].isnull()).sum(dim="time")
            mask_valid = valid_days >= min_days_required
        else:
            mask_valid = True

        # Aplicar método de agregação
        agg_func = getattr(pentad_data, method)
        aggregated = agg_func(dim="time", skipna=True)

        # Aplicar máscara de dias mínimos
        if "olr" in aggregated.data_vars:
            if isinstance(mask_valid, xr.DataArray):
                aggregated["olr"] = aggregated["olr"].where(mask_valid)
            elif not mask_valid:
                aggregated["olr"] = xr.full_like(aggregated["olr"], np.nan)

        return aggregated

    def _create_empty_pentad(self, template_data: xr.Dataset) -> xr.Dataset:
        """Cria uma pentada vazia com estrutura correta."""
        # Remover dimensões temporais
        coords = {
            k: v
            for k, v in template_data.coords.items()
            if k not in ["time", "pentad_number"]
        }

        # Criar variáveis preenchidas com NaN
        data_vars = {}
        for var_name, data_arr in template_data.data_vars.items():
            non_time_dims = [d for d in data_arr.dims if d != "time"]
            non_time_shape = [data_arr.sizes[d] for d in non_time_dims]
            non_time_coords = {
                k: v for k, v in data_arr.coords.items() if k in non_time_dims
            }

            data_vars[var_name] = xr.DataArray(
                np.full(non_time_shape, np.nan),
                coords=non_time_coords,
                dims=non_time_dims,
                name=var_name,
            )

        return xr.Dataset(data_vars, coords=coords)

    def _add_pentad_metadata(
        self,
        pentad_dataset: xr.Dataset,
        year: int,
        method: str,
        min_days_required: int,
        remove_leap_days: bool,
    ) -> xr.Dataset:
        """
        Adiciona metadados e coordenadas temporais ao dataset de pentadas.

        COMPATÍVEL COM:
        - pentada_to_dates() retornando datetime.datetime
        - pentada_to_dates() retornando cftime (futuro)
        """
        # Adicionar coordenada de tempo representativa
        time_coords = []
        for pentad_num in pentad_dataset.pentada.values:
            start_date, end_date = pentada_to_dates(pentad_num, year)
            center_date = start_date + (end_date - start_date) / 2

            # ================================================================
            # CONVERSÃO ROBUSTA - COMPATÍVEL COM datetime E cftime
            # ================================================================
            try:
                # Método 1: Conversão direta via pandas (funciona com datetime)
                center_timestamp = pd.Timestamp(center_date)
            except (ValueError, TypeError):
                # Método 2: Fallback para cftime ou outros tipos
                if hasattr(center_date, "year"):
                    center_timestamp = pd.Timestamp(
                        year=center_date.year,
                        month=center_date.month,
                        day=center_date.day,
                        hour=getattr(center_date, "hour", 12),
                        minute=getattr(center_date, "minute", 0),
                    )
                else:
                    raise RuntimeError(
                        f"Não foi possível converter data da pentada. "
                        f"Tipo: {type(center_date)}"
                    )

            time_coords.append(np.datetime64(center_timestamp, "us"))

        pentad_dataset = pentad_dataset.assign_coords(time=("pentada", time_coords))

        # Adicionar atributos globais
        pentad_dataset.attrs.update(
            {
                "processed_year": year,
                "creation_date_utc": datetime.utcnow().isoformat() + "Z",
                "pentad_aggregation_method": method,
                "min_days_for_pentad_calculation": min_days_required,
                "leap_days_removed": remove_leap_days,
                "history": (
                    f"Pentads created by LOCZCIT DataProcessor on "
                    f"{datetime.utcnow():%Y-%m-%d %H:%M:%S UTC}"
                ),
            }
        )

        # Computar resultados Dask se necessário
        if self.use_dask:
            has_dask_arrays = any(
                isinstance(arr.data, da.Array)
                for arr in pentad_dataset.data_vars.values()
            )
            if has_dask_arrays:
                logger.info("Computando resultados Dask...")
                pentad_dataset = pentad_dataset.compute()

        return pentad_dataset

    def create_recent_average(
        self,
        olr_data: xr.Dataset,
        start_date: str,
        end_date: str,
        method: str = "mean",
        min_valid_ratio: float = 0.5,
        weights: xr.DataArray | None = None,
    ) -> xr.DataArray:
        """
        Cria média de OLR para um período recente.


        Parameters
        ----------
        olr_data : xr.Dataset
            Dataset com dados de OLR
        start_date : str
            Data inicial (formato ISO: YYYY-MM-DD)
        end_date : str
            Data final (formato ISO: YYYY-MM-DD)
        method : str, default "mean"
            Método: "mean", "median", "min", "max", "weighted_mean"
        min_valid_ratio : float, default 0.5
            Proporção mínima de dias válidos (0-1)
        weights : xr.DataArray, optional
            Pesos para média ponderada

        Returns
        -------
        xr.DataArray
            Média calculada para o período
        """
        # Validar datas
        start_dt = validate_date(start_date)
        end_dt = validate_date(end_date)

        if end_dt < start_dt:
            raise ValueError("Data final deve ser posterior à inicial")

        # Validar dataset
        if "olr" not in olr_data:
            raise ValueError("Variável 'olr' não encontrada")
        if "time" not in olr_data.coords:
            raise ValueError("Coordenada 'time' não encontrada")

        # Selecionar período
        period_data = self._select_time_period(olr_data, start_dt, end_dt)

        if len(period_data.time) == 0:
            raise ValueError(
                f"Nenhum dado encontrado para o período "
                f"{start_dt.date()} - {end_dt.date()}"
            )

        logger.info(
            f"Calculando {method} para {len(period_data.time)} dias "
            f"({start_dt.date()} a {end_dt.date()})"
        )

        # Calcular estatística
        result = self._calculate_temporal_statistic(
            period_data["olr"], method, weights, min_valid_ratio
        )

        # Adicionar metadados
        result.attrs.update(
            {
                "period_start": start_dt.isoformat(),
                "period_end": end_dt.isoformat(),
                "days_in_period": len(period_data.time),
                "aggregation_method": method,
                "min_valid_ratio": min_valid_ratio,
            }
        )

        return result

    def process_latest_period(
        self,
        olr_data: xr.Dataset,
        num_days: int = 5,
        min_valid_ratio: float = 0.6,
    ) -> xr.DataArray:
        """
        Calcula a média dos últimos 'num_days' disponíveis no dataset.

        COMPATÍVEL COM:
        - ERA5 (datetime64[ns])
        - NOAA (cftime.DatetimeGregorian)
        """
        if "time" not in olr_data.coords or len(olr_data.time) == 0:
            raise ValueError("Dataset inválido ou sem coordenada de tempo.")

        # ================================================================
        # CONVERSÃO ROBUSTA DE DATA - COMPATÍVEL COM ERA5 E NOAA
        # ================================================================

        max_time_value = olr_data.time.max().values

        try:
            # Método 1: Conversão direta via pandas
            latest_date = pd.Timestamp(max_time_value)

            if not all(hasattr(latest_date, attr) for attr in ["year", "month", "day"]):
                raise ValueError("Timestamp não tem atributos de data")

        except (ValueError, TypeError) as e:
            # Método 2: Fallback para tipos especiais
            try:
                if isinstance(max_time_value, np.datetime64):
                    latest_date = pd.to_datetime(max_time_value)
                elif hasattr(max_time_value, "year"):
                    latest_date = pd.Timestamp(
                        year=max_time_value.year,
                        month=max_time_value.month,
                        day=max_time_value.day,
                    )
                else:
                    raise ValueError(
                        f"Tipo de tempo não suportado: {type(max_time_value)}"
                    )
            except Exception as e2:
                raise RuntimeError(
                    f"Não foi possível converter coordenada temporal. "
                    f"Tipo: {type(max_time_value)}, Erro original: {e}, "
                    f"Erro fallback: {e2}"
                )

        # Calcular data inicial
        start_date = latest_date - pd.Timedelta(days=num_days - 1)

        logger.info(
            f"Processando os últimos {num_days} dias: "
            f"{start_date.strftime('%Y-%m-%d')} a {latest_date.strftime('%Y-%m-%d')}"
        )

        return self.create_recent_average(
            olr_data=olr_data,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=latest_date.strftime("%Y-%m-%d"),
            method="mean",
            min_valid_ratio=min_valid_ratio,
        )

    def _select_time_period(
        self,
        data: xr.Dataset,
        start_date: datetime,
        end_date: datetime,
    ) -> xr.Dataset:
        """Seleciona dados em um período específico."""
        time_values = data.time.values

        # Ajustar para o tipo de calendário dos dados
        if HAS_CFTIME and time_values.size > 0:
            if isinstance(time_values[0], cftime.datetime):
                calendar = time_values[0].calendar
                start = cftime.datetime(
                    start_date.year,
                    start_date.month,
                    start_date.day,
                    calendar=calendar,
                )
                end = cftime.datetime(
                    end_date.year,
                    end_date.month,
                    end_date.day,
                    23,
                    59,
                    59,
                    calendar=calendar,
                )
            else:
                start = datetime(start_date.year, start_date.month, start_date.day)
                end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
        else:
            start = start_date
            end = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)

        return data.sel(time=slice(start, end))

    def _calculate_temporal_statistic(
        self,
        data: xr.DataArray,
        method: str,
        weights: xr.DataArray | None,
        min_valid_ratio: float,
    ) -> xr.DataArray:
        """Calcula estatística temporal com validação de dados."""
        # Calcular proporção de dados válidos
        valid_mask = ~data.isnull()
        valid_ratio = valid_mask.sum(dim="time") / len(data.time)

        # Aplicar método de agregação
        if method == "mean":
            result = data.mean(dim="time", skipna=True)
        elif method == "median":
            result = data.median(dim="time", skipna=True)
        elif method == "min":
            result = data.min(dim="time", skipna=True)
        elif method == "max":
            result = data.max(dim="time", skipna=True)
        elif method == "weighted_mean":
            if weights is None:
                raise ValueError("Pesos necessários para média ponderada")
            result = self._weighted_mean(data, weights, valid_mask)
        else:
            raise ValueError(f"Método '{method}' inválido")

        # Aplicar máscara de proporção mínima
        result = result.where(valid_ratio >= min_valid_ratio)

        return result

    def _weighted_mean(
        self,
        data: xr.DataArray,
        weights: xr.DataArray,
        valid_mask: xr.DataArray,
    ) -> xr.DataArray:
        """Calcula média ponderada considerando valores válidos."""
        try:
            # Alinhar pesos com os dados
            aligned_weights = weights.broadcast_like(data)
        except ValueError:
            # Tentar broadcast manual se as dimensões espaciais corresponderem
            if set(weights.dims) == set(data.dims) - {"time"}:
                aligned_weights = weights
            else:
                raise ValueError(
                    f"Dimensões dos pesos {weights.dims} incompatíveis "
                    f"com dados {data.dims}"
                )

        # Aplicar máscara de valores válidos aos pesos
        masked_weights = aligned_weights.where(valid_mask)

        # Calcular média ponderada
        weighted_sum = (data * masked_weights).sum(dim="time", skipna=True)
        weights_sum = masked_weights.sum(dim="time", skipna=True)

        # Evitar divisão por zero
        return weighted_sum / weights_sum.where(weights_sum != 0)

    def find_minimum_coordinates(
        self,
        data_array: xr.DataArray,
        threshold: float | None = None,
        search_radius: int = 1,
        method: str = "column_minimum",
        olr_valid_range: tuple[float, float] = (50.0, 450.0),
        study_area_path: PathLike | None = None,
        lat_bounds: tuple[float, float] | None = None,
        lon_bounds: tuple[float, float] | None = None,
    ) -> list[Coordinate]:
        """
        Identifica coordenadas com valores mínimos de OLR.

        Como encontrar os "vales mais profundos" em um mapa topográfico,
        onde cada vale representa uma região de baixa radiação (e
        potencialmente alta convecção).

        Parameters
        ----------
        data_array : xr.DataArray
            Array 2D (lat, lon) com valores de OLR
        threshold : float, optional
            Valor máximo de OLR para considerar
        search_radius : int, default 1
            Raio em pixels para verificar mínimos locais
        method : str, default "column_minimum"
            Método: "column_minimum", "local_minimum", "combined"
        olr_valid_range : tuple, default (50.0, 450.0)
            Faixa válida de valores de OLR
        study_area_path : str or Path, optional
            Caminho para arquivo de área de estudo
        lat_bounds : tuple, optional
            Limites de latitude (min, max)
        lon_bounds : tuple, optional
            Limites de longitude (min, max)

        Returns
        -------
        List[Tuple[float, float]]
            Lista de coordenadas (lon, lat) dos mínimos encontrados
        """
        logger.info(
            f"Buscando mínimos de OLR (método: {method}, "
            f"threshold: {threshold}, raio: {search_radius}px)"
        )

        # Validar entrada
        self._validate_2d_array(data_array)

        # Preparar dados
        olr_values = data_array.values.copy()
        lats = data_array.lat.values
        lons = data_array.lon.values

        # Validar e mascarar valores de OLR
        olr_values = validate_olr_values(olr_values, valid_range=olr_valid_range)

        # Criar máscara de processamento
        process_mask = self._create_processing_mask(
            olr_values,
            threshold,
            data_array,
            study_area_path,
            lat_bounds,
            lon_bounds,
        )

        # Encontrar mínimos
        coordinates = []

        if method in ["column_minimum", "combined"]:
            coords = self._find_column_minima(
                olr_values, lats, lons, process_mask, search_radius
            )
            coordinates.extend(coords)

        if method in ["local_minimum", "combined"]:
            coords = self._find_local_minima(
                olr_values, lats, lons, process_mask, search_radius
            )
            coordinates.extend(coords)

        if method not in ["column_minimum", "local_minimum", "combined"]:
            raise ValueError(f"Método '{method}' não reconhecido")

        # Remover duplicatas se método combinado
        if method == "combined" and coordinates:
            coordinates = list(dict.fromkeys(coordinates))

        logger.info(f"Encontradas {len(coordinates)} coordenadas de mínimo")
        return coordinates

    def _validate_2d_array(self, data_array: xr.DataArray) -> None:
        """Valida que o array é 2D com dimensões lat/lon."""
        if not isinstance(data_array, xr.DataArray):
            raise TypeError("Entrada deve ser xr.DataArray")

        if data_array.ndim != 2:
            raise ValueError(f"Array deve ser 2D, encontrado {data_array.ndim}D")

        if not all(d in data_array.dims for d in ["lat", "lon"]):
            raise ValueError(
                f"Array deve ter dimensões 'lat' e 'lon', encontrado: {data_array.dims}"
            )

    def _create_processing_mask(
        self,
        olr_values: np.ndarray,
        threshold: float | None,
        data_array: xr.DataArray,
        study_area_path: PathLike | None,
        lat_bounds: tuple[float, float] | None,
        lon_bounds: tuple[float, float] | None,
    ) -> np.ndarray:
        """Cria máscara indicando quais pixels processar."""
        # Iniciar com pixels válidos (não-NaN)
        mask = ~np.isnan(olr_values)

        # Aplicar threshold se fornecido
        if threshold is not None:
            logger.info(f"Aplicando threshold OLR <= {threshold} W/m²")
            mask &= olr_values <= threshold

        # Aplicar restrição geográfica
        geo_applied = False

        if lat_bounds is not None and lon_bounds is not None:
            # Restrição retangular
            mask &= self._create_rectangular_mask(data_array, lat_bounds, lon_bounds)
            geo_applied = True
        else:
            # Tentar usar área de estudo
            area_path = self._resolve_study_area_path(study_area_path)
            if area_path:
                try:
                    mask &= self._create_geometry_mask(data_array, area_path)
                    geo_applied = True
                except Exception as e:
                    logger.error(f"Erro ao aplicar área de estudo: {e}")

        if not geo_applied:
            logger.info("Nenhuma restrição geográfica aplicada")

        return mask

    def _create_rectangular_mask(
        self,
        data_array: xr.DataArray,
        lat_bounds: tuple[float, float],
        lon_bounds: tuple[float, float],
    ) -> np.ndarray:
        """Cria máscara retangular baseada em limites lat/lon."""
        lat_min, lat_max, lon_min, lon_max = validate_coordinates(
            (*lat_bounds, *lon_bounds)
        )

        logger.info(
            f"Aplicando limites: Lat ({lat_min}, {lat_max}), Lon ({lon_min}, {lon_max})"
        )

        # Criar meshgrid para comparação
        lon_mesh, lat_mesh = np.meshgrid(data_array.lon.values, data_array.lat.values)

        lat_mask = (lat_mesh >= lat_min) & (lat_mesh <= lat_max)
        lon_mask = (lon_mesh >= lon_min) & (lon_mesh <= lon_max)

        return lat_mask & lon_mask

    def _resolve_study_area_path(self, study_area_path: PathLike | None) -> Path | None:
        """Resolve o caminho da área de estudo."""
        if study_area_path:
            return Path(study_area_path)
        if self.default_study_area_path:
            return self.default_study_area_path
        return None

    def _create_geometry_mask(
        self,
        data_array: xr.DataArray,
        area_path: Path,
    ) -> np.ndarray:
        """Cria máscara a partir de arquivo de geometria."""
        if not HAS_GEOPANDAS:
            raise ImportError("GeoPandas necessário para carregar área de estudo")

        logger.info(f"Carregando área de estudo de: {area_path}")

        if area_path.suffix.lower() == ".parquet":
            gdf = gpd.read_parquet(area_path)
        else:
            gdf = gpd.read_file(area_path)

        return self._create_mask_from_geometry(data_array, gdf).values

    def _find_column_minima(
        self,
        olr_values: np.ndarray,
        lats: np.ndarray,
        lons: np.ndarray,
        mask: np.ndarray,
        radius: int,
    ) -> list[Coordinate]:
        """
        Encontra mínimos por coluna (longitude).

        Como procurar o ponto mais baixo em cada "fatia vertical"
        do mapa.
        """
        coords = []

        for j, lon in enumerate(lons):
            column = olr_values[:, j]
            column_mask = mask[:, j]

            if not np.any(column_mask):
                continue

            # Encontrar mínimo na coluna
            masked_column = np.where(column_mask, column, np.inf)
            if np.all(np.isinf(masked_column)):
                continue

            i_min = np.argmin(masked_column)

            # Verificar se é mínimo local
            if radius > 0:
                if not self._is_local_minimum(olr_values, (i_min, j), radius, mask):
                    continue

            coords.append((float(lon), float(lats[i_min])))

        return coords

    def _find_local_minima(
        #
        self,
        olr_values: np.ndarray,
        lats: np.ndarray,
        lons: np.ndarray,
        mask: np.ndarray,
        radius: int,
    ) -> list[Coordinate]:
        """
        Encontra mínimos locais usando filtro.

        Como identificar "depressões" no terreno que são mais baixas
        que todos os pontos ao redor.
        """
        try:
            from scipy.ndimage import minimum_filter
        except ImportError:
            logger.error("scipy.ndimage necessário para método 'local_minimum'")
            return []

        # Preparar dados para filtro
        data_for_filter = np.where(mask, olr_values, np.inf)

        # Tamanho do filtro baseado no raio
        filter_size = max(1, 2 * radius + 1)

        # Aplicar filtro de mínimo
        # CORREÇÃO: scipy.ndimage.minimum_filter não aceita 'constant_values'
        # Use o parâmetro 'mode' com 'constant' e 'cval'
        local_mins = minimum_filter(
            data_for_filter,
            size=filter_size,
            mode="constant",
            cval=np.inf,  # Valor constante para bordas
        )

        # Encontrar onde o valor original é igual ao mínimo local
        is_local_min = (data_for_filter == local_mins) & mask

        # Extrair coordenadas
        coords = []
        min_indices = np.where(is_local_min)

        for i, j in zip(min_indices[0], min_indices[1], strict=False):
            coords.append((float(lons[j]), float(lats[i])))

        return coords

    def _is_local_minimum(
        self,
        data: np.ndarray,
        position: tuple[int, int],
        radius: int,
        mask: np.ndarray,
    ) -> bool:
        """Verifica se uma posição é mínimo local dentro do raio."""
        i, j = position
        center_value = data[i, j]

        if not mask[i, j] or np.isnan(center_value):
            return False

        # Definir janela de busca
        i_min = max(0, i - radius)
        i_max = min(data.shape[0], i + radius + 1)
        j_min = max(0, j - radius)
        j_max = min(data.shape[1], j + radius + 1)

        # Verificar todos os vizinhos
        for ii in range(i_min, i_max):
            for jj in range(j_min, j_max):
                if ii == i and jj == j:
                    continue

                if mask[ii, jj]:
                    neighbor_value = data[ii, jj]
                    if not np.isnan(neighbor_value) and neighbor_value < center_value:
                        return False

        return True

    def create_hovmoller_data_daily(
        self, daily_data: xr.Dataset, longitude: float
    ) -> xr.DataArray:
        """
        Cria dados para diagrama de Hovmöller a partir de dados diários.

        Parameters
        ----------
        daily_data : xr.Dataset
            Dataset com dados diários de OLR e dimensões 'time', 'lat', 'lon'.
        longitude : float
            Longitude para o corte do diagrama.

        Returns
        -------
        xr.DataArray
            Dados 2D (time, lat) prontos para a plotagem do Hovmöller.
        """
        if "olr" not in daily_data or not all(
            d in daily_data.dims for d in ["time", "lat", "lon"]
        ):
            raise ValueError(
                "Dataset diário inválido. Dimensões 'time', 'lat', 'lon' e variável 'olr' são necessárias."
            )

        logger.info(
            f"Criando dados de Hovmöller diário para longitude {longitude:.2f}°"
        )

        # Seleciona os dados na longitude especificada
        hov_data = daily_data["olr"].sel(lon=longitude, method="nearest")

        # Garante que a saída tenha as dimensões corretas para a plotagem
        return hov_data.transpose("time", "lat")

    def apply_mask(
        self,
        data: xr.DataArray,
        mask_source: MaskSource | None = None,
        lat_bounds: tuple[float, float] | None = None,
        lon_bounds: tuple[float, float] | None = None,
        buffer_degrees: float = 0.0,
        invert: bool = False,
        fill_value: Any = np.nan,
    ) -> xr.DataArray:
        """
        Aplica máscara geográfica aos dados.

        Como usar um "estêncil" para pintar apenas as áreas de interesse
        em um mapa, deixando o resto em branco.

        Parameters
        ----------
        data : xr.DataArray
            Dados para mascarar
        mask_source : various types, optional
            Fonte da máscara (arquivo, GeoDataFrame, ou DataArray)
        lat_bounds : tuple, optional
            Limites de latitude para máscara retangular
        lon_bounds : tuple, optional
            Limites de longitude para máscara retangular
        buffer_degrees : float, default 0.0
            Buffer em graus para expandir/contrair a máscara
        invert : bool, default False
            Se True, inverte a máscara (mantém fora, remove dentro)
        fill_value : Any, default np.nan
            Valor para preencher áreas mascaradas

        Returns
        -------
        xr.DataArray
            Dados com máscara aplicada
        """
        logger.info(
            f"Aplicando máscara (buffer: {buffer_degrees}°, "
            f"inverter: {invert}, preenchimento: {fill_value})"
        )

        # Validar entrada
        if not all(d in data.dims for d in ["lat", "lon"]):
            raise ValueError("DataArray deve ter dimensões 'lat' e 'lon'")

        # Determinar máscara
        mask = self._determine_mask(
            data, mask_source, lat_bounds, lon_bounds, buffer_degrees
        )

        # Aplicar inversão se solicitado
        if invert:
            logger.info("Invertendo máscara")
            mask = ~mask

        # Aplicar máscara
        masked_data = data.where(mask, other=fill_value)

        # Preservar e adicionar metadados
        masked_data.attrs.update(data.attrs)
        masked_data.attrs["mask_applied"] = {
            "inverted": invert,
            "fill_value": str(fill_value),
            "buffer_degrees": buffer_degrees,
        }

        # Estatísticas de mascaramento
        self._log_mask_statistics(data, masked_data, mask, fill_value)

        return masked_data

    def _determine_mask(
        self,
        data: xr.DataArray,
        mask_source: MaskSource | None,
        lat_bounds: tuple[float, float] | None,
        lon_bounds: tuple[float, float] | None,
        buffer_degrees: float,
    ) -> xr.DataArray:
        """Determina a máscara apropriada baseada nas entradas."""
        # Prioridade 1: mask_source explícito
        if mask_source is not None:
            return self._process_mask_source(data, mask_source, buffer_degrees)

        # Prioridade 2: limites retangulares
        if lat_bounds is not None and lon_bounds is not None:
            return self._create_bounds_mask(data, lat_bounds, lon_bounds)

        # Prioridade 3: área de estudo padrão
        if self.default_study_area_path and self.default_study_area_path.exists():
            logger.info("Usando área de estudo padrão")
            return self._process_mask_source(
                data, self.default_study_area_path, buffer_degrees
            )

        raise ValueError(
            "Nenhuma fonte de máscara válida. Forneça mask_source, "
            "lat/lon_bounds, ou configure área de estudo padrão."
        )

    def _process_mask_source(
        self,
        data: xr.DataArray,
        mask_source: MaskSource,
        buffer_degrees: float,
    ) -> xr.DataArray:
        """Processa diferentes tipos de fonte de máscara."""
        if isinstance(mask_source, (str, Path)):
            # Arquivo de geometria
            path = Path(mask_source)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")

            if not HAS_GEOPANDAS:
                raise ImportError("GeoPandas necessário para ler máscaras")

            if path.suffix.lower() == ".parquet":
                gdf = gpd.read_parquet(path)
            else:
                gdf = gpd.read_file(path)

            if buffer_degrees != 0:
                gdf = self._apply_buffer_to_gdf(gdf, buffer_degrees)

            return self._create_mask_from_geometry(data, gdf)

        if HAS_GEOPANDAS and isinstance(mask_source, gpd.GeoDataFrame):
            # GeoDataFrame direto
            gdf = mask_source.copy()
            if buffer_degrees != 0:
                gdf = self._apply_buffer_to_gdf(gdf, buffer_degrees)
            return self._create_mask_from_geometry(data, gdf)

        if isinstance(mask_source, xr.DataArray):
            # DataArray booleano
            self._validate_mask_array(mask_source, data)
            return mask_source.astype(bool)

        raise TypeError(f"Tipo de mask_source não suportado: {type(mask_source)}")

    def _apply_buffer_to_gdf(
        self, gdf: gpd.GeoDataFrame, buffer_degrees: float
    ) -> gpd.GeoDataFrame:
        """Aplica buffer à geometria."""
        logger.debug(f"Aplicando buffer de {buffer_degrees}°")

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Geometry is in a geographic CRS.",
                category=UserWarning,
            )
            gdf["geometry"] = gdf.geometry.buffer(buffer_degrees)

        return gdf

    def _create_bounds_mask(
        self,
        data: xr.DataArray,
        lat_bounds: tuple[float, float],
        lon_bounds: tuple[float, float],
    ) -> xr.DataArray:
        """Cria máscara retangular a partir de limites."""
        logger.info(f"Criando máscara retangular: Lat {lat_bounds}, Lon {lon_bounds}")

        # Validar e ordenar limites
        lat_sorted = sorted(lat_bounds)
        lon_sorted = sorted(lon_bounds)
        lat_min, lat_max, lon_min, lon_max = validate_coordinates(
            (*lat_sorted, *lon_sorted)
        )

        # Criar condições
        lat_cond = (data.lat >= lat_min) & (data.lat <= lat_max)
        lon_cond = (data.lon >= lon_min) & (data.lon <= lon_max)

        # Combinar condições
        return lat_cond & lon_cond

    def _validate_mask_array(self, mask: xr.DataArray, data: xr.DataArray) -> None:
        """Valida compatibilidade entre máscara e dados."""
        spatial_dims = {"lat", "lon"}

        # Verificar dimensões
        mask_spatial_dims = set(mask.dims) & spatial_dims
        if not spatial_dims.issubset(mask_spatial_dims):
            raise ValueError(
                f"Máscara deve ter dimensões 'lat' e 'lon', encontrado: {mask.dims}"
            )

        # Verificar tamanhos
        for dim in spatial_dims:
            if data.sizes[dim] != mask.sizes[dim]:
                raise ValueError(
                    f"Tamanho da dimensão '{dim}' incompatível: "
                    f"dados={data.sizes[dim]}, máscara={mask.sizes[dim]}"
                )

    def _create_mask_from_geometry(
        self,
        data_array: xr.DataArray,
        gdf: gpd.GeoDataFrame,
    ) -> xr.DataArray:
        """
        Cria máscara xarray a partir de GeoDataFrame.

        Como converter um "desenho vetorial" (geometria) em uma
        "imagem raster" (grade de pixels) que se alinha com os dados.
        """
        if not HAS_GEOPANDAS:
            raise ImportError("GeoPandas necessário")

        # Garantir CRS
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)

        # Verificar e ajustar convenção de longitude se necessário
        gdf = self._adjust_longitude_convention(gdf, data_array)

        if HAS_REGIONMASK:
            logger.debug("Usando regionmask para criar máscara")
            mask_values = rm.mask_geopandas(gdf, data_array.lon, data_array.lat)
            return mask_values.notnull()
        logger.debug("Usando método ponto-a-ponto (mais lento)")
        return self._create_mask_pointwise(data_array, gdf)

    def _adjust_longitude_convention(
        self,
        gdf: gpd.GeoDataFrame,
        data_array: xr.DataArray,
    ) -> gpd.GeoDataFrame:
        """Ajusta convenção de longitude entre [-180,180] e [0,360]."""
        data_lon_min = float(data_array.lon.min())
        data_lon_max = float(data_array.lon.max())
        gdf_lon_min = gdf.total_bounds[0]

        # Detectar e ajustar se necessário
        if data_lon_min >= -0.1 and data_lon_max > 180.1:  # Dados em [0,360]
            if gdf_lon_min < -0.1:  # GDF em [-180,180]
                logger.info("Ajustando GeoDataFrame para longitude [0,360]")
                from shapely.ops import transform

                def to_0_360(x, y, z=None):
                    return (x + 360) % 360, y

                gdf = gdf.copy()
                gdf.geometry = gdf.geometry.map(lambda geom: transform(to_0_360, geom))

        elif data_lon_min < -0.1 and data_lon_max < 180.1:  # Dados em [-180,180]
            if gdf_lon_min >= -0.1 and gdf.total_bounds[2] > 180.1:  # GDF em [0,360]
                logger.info("Ajustando GeoDataFrame para longitude [-180,180]")
                from shapely.ops import transform

                def to_minus_180_180(x, y, z=None):
                    return x if x <= 180 else x - 360, y

                gdf = gdf.copy()
                gdf.geometry = gdf.geometry.map(
                    lambda geom: transform(to_minus_180_180, geom)
                )

        return gdf

    def _create_mask_pointwise(
        self,
        data_array: xr.DataArray,
        gdf: gpd.GeoDataFrame,
    ) -> xr.DataArray:
        """Cria máscara verificando cada ponto individualmente."""
        from shapely.geometry import Point

        lons = data_array.lon.values
        lats = data_array.lat.values
        mask = np.zeros((len(lats), len(lons)), dtype=bool)

        # Unificar geometrias
        unified_geom = gdf.unary_union
        if not unified_geom.is_valid:
            unified_geom = unified_geom.buffer(0)

        # Verificar cada ponto
        for i, lat in enumerate(
            tqdm(
                lats,
                desc="Criando máscara",
                disable=not logger.isEnabledFor(logging.DEBUG),
            )
        ):
            for j, lon in enumerate(lons):
                if unified_geom.contains(Point(lon, lat)):
                    mask[i, j] = True

        return xr.DataArray(
            mask,
            coords={"lat": lats, "lon": lons},
            dims=["lat", "lon"],
        )

    def _log_mask_statistics(
        self,
        original: xr.DataArray,
        masked: xr.DataArray,
        mask: xr.DataArray,
        fill_value: Any,
    ) -> None:
        """Calcula e registra estatísticas do mascaramento."""
        try:
            valid_before = int(original.notnull().sum())
            valid_after = int(masked.notnull().sum())

            if isinstance(fill_value, float) and np.isnan(fill_value):
                affected = int((~mask & original.notnull()).sum())
            else:
                affected = int((~mask).sum())

            logger.info(
                f"Máscara aplicada: {valid_before} → {valid_after} "
                f"valores válidos. {affected} pixels preenchidos."
            )
        except Exception as e:
            logger.warning(f"Erro ao calcular estatísticas: {e}")

    def create_hovmoller_data(
        self,
        pentad_dataset: xr.Dataset,
        longitude: float,
        target_years: int | list[int] | None = None,
        smooth_temporally: bool = True,
    ) -> xr.DataArray:
        """
        Cria dados para diagrama de Hovmöller.

        Como criar um "corte temporal" dos dados, mostrando como a
        ZCIT se move ao longo do ano em uma longitude específica.

        Parameters
        ----------
        pentad_dataset : xr.Dataset
            Dataset de pentadas com variável 'olr'
        longitude : float
            Longitude para o corte
        target_years : int or list, optional
            Anos específicos ou None para climatologia
        smooth_temporally : bool, default True
            Se True, aplica suavização temporal

        Returns
        -------
        xr.DataArray
            Dados 2D (lat, pentada) para plotagem
        """
        # Validar entrada
        if "olr" not in pentad_dataset:
            raise ValueError("Variável 'olr' não encontrada")
        if "lon" not in pentad_dataset.coords:
            raise ValueError("Coordenada 'lon' não encontrada")
        if "pentada" not in pentad_dataset.dims:
            raise ValueError("Dimensão 'pentada' não encontrada")

        # Selecionar longitude
        data_at_lon = pentad_dataset["olr"].sel(lon=longitude, method="nearest")
        actual_lon = float(data_at_lon.lon)

        logger.info(
            f"Criando Hovmöller para longitude {actual_lon:.2f}° "
            f"(solicitado: {longitude:.2f}°)"
        )

        # Processar anos se necessário
        plot_data = self._process_hovmoller_years(
            data_at_lon.copy(deep=True), target_years
        )

        # Garantir dimensões corretas
        plot_data = self._ensure_hovmoller_dims(plot_data)

        # Aplicar suavização temporal
        if smooth_temporally and "pentada" in plot_data.dims:
            plot_data = plot_data.rolling(pentada=3, center=True, min_periods=1).mean(
                skipna=True
            )
            logger.info("Suavização temporal aplicada (3 pentadas)")

        # Adicionar metadados
        plot_data.attrs.update(
            {
                "longitude_requested": longitude,
                "longitude_actual": actual_lon,
                "diagram_type": "Hovmöller",
                "smooth_temporal": smooth_temporally,
                "years": str(target_years) if target_years else "climatologia",
            }
        )

        # Reordenar dimensões para plotagem (lat no eixo Y, pentada no X)
        return plot_data.transpose("lat", "pentada", ...)

    def _process_hovmoller_years(
        self,
        data: xr.DataArray,
        target_years: int | list[int] | None,
    ) -> xr.DataArray:
        """Processa seleção/agregação de anos para Hovmöller."""
        if "year" not in data.dims and "year" not in data.coords:
            return data

        if target_years is not None:
            if isinstance(target_years, int):
                target_years = [target_years]

            try:
                data = data.sel(year=target_years)
                if len(target_years) > 1 and "year" in data.dims:
                    data = data.mean(dim="year", skipna=True)
                    logger.info(f"Hovmöller: média dos anos {target_years}")
                else:
                    logger.info(f"Hovmöller: ano {target_years[0]}")
            except Exception as e:
                logger.warning(
                    f"Erro ao selecionar anos {target_years}: {e}. "
                    "Usando média de todos os anos."
                )
                if "year" in data.dims:
                    data = data.mean(dim="year", skipna=True)
        elif "year" in data.dims:
            data = data.mean(dim="year", skipna=True)
            logger.info("Hovmöller: climatologia de todos os anos")

        return data

    def _ensure_hovmoller_dims(self, data: xr.DataArray) -> xr.DataArray:
        """Garante que dados tenham apenas dimensões lat e pentada."""
        expected_dims = {"lat", "pentada"}
        current_dims = set(data.dims)

        extra_dims = list(current_dims - expected_dims)
        if extra_dims:
            logger.warning(f"Removendo dimensões extras {extra_dims} via média")
            data = data.mean(dim=extra_dims, skipna=True)

        return data

    def interpolate_missing_data(
        self,
        data: xr.DataArray,
        method: str = "linear",
        limit: int | None = None,
        dim: str | list[str] | None = None,
        use_coordinate: bool | str = True,
        fill_value: Any | None = None,
    ) -> xr.DataArray:
        """
        Interpola dados faltantes.

        Como "preencher os espaços em branco" de um quebra-cabeça
        usando as peças vizinhas como referência.

        Parameters
        ----------
        data : xr.DataArray
            Dados com valores faltantes (NaN)
        method : str, default "linear"
            Método de interpolação: "linear", "nearest", "cubic"
        limit : int, optional
            Número máximo de NaNs consecutivos para interpolar
        dim : str or list, optional
            Dimensões para interpolar (None = todas)
        use_coordinate : bool or str, default True
            Se True, usa valores das coordenadas para interpolação
        fill_value : Any, optional
            Valor para extrapolação ou "extrapolate"

        Returns
        -------
        xr.DataArray
            Dados com valores interpolados
        """
        if not isinstance(data, xr.DataArray):
            raise TypeError("Entrada deve ser xr.DataArray")

        missing_before = int(data.isnull().sum())
        if missing_before == 0:
            logger.info("Nenhum dado faltante para interpolar")
            return data.copy(deep=True)

        logger.info(
            f"Interpolando {missing_before} valores faltantes "
            f"(método: {method}, limite: {limit})"
        )

        # Realizar interpolação
        interpolated = data.interpolate_na(
            dim=dim,
            method=method,
            limit=limit,
            use_coordinate=use_coordinate,
            fill_value=fill_value,
        )

        missing_after = int(interpolated.isnull().sum())
        filled_count = missing_before - missing_after

        # Preservar e atualizar metadados
        interpolated.attrs.update(data.attrs)
        interpolated.attrs["interpolation_info"] = {
            "method": method,
            "limit": limit,
            "dimensions": dim or "all",
            "use_coordinate": use_coordinate,
            "fill_value": fill_value,
            "missing_before": missing_before,
            "missing_after": missing_after,
            "filled": filled_count,
        }

        logger.info(f"Interpolação concluída: {filled_count} valores preenchidos")

        return interpolated

    def calculate_statistics(
        self,
        data: xr.DataArray,
        stats: list[str] | None = None,
        dim: str | list[str] | None = None,
        weights: xr.DataArray | None = None,
    ) -> dict[str, float | xr.DataArray]:
        """
        Calcula estatísticas dos dados.

        Como gerar um "relatório resumido" dos dados, incluindo
        médias, desvios, percentis e outras métricas importantes.

        Parameters
        ----------
        data : xr.DataArray
            Dados para análise
        stats : list, optional
            Estatísticas a calcular. Se None, calcula padrão
        dim : str or list, optional
            Dimensões para redução. None mantém todas
        weights : xr.DataArray, optional
            Pesos para estatísticas ponderadas

        Returns
        -------
        Dict[str, Union[float, xr.DataArray]]
            Dicionário com estatísticas calculadas
        """
        if stats is None:
            stats = ["mean", "std", "min", "max", "median", "count"]

        logger.info(
            f"Calculando estatísticas: {stats} (dimensões: {dim or 'mantidas'})"
        )

        results = {}

        # Estatísticas básicas
        if "mean" in stats:
            if weights is not None:
                weighted_data = data * weights
                weights_sum = weights.sum(dim=dim, skipna=True)
                results["mean"] = weighted_data.sum(
                    dim=dim, skipna=True
                ) / weights_sum.where(weights_sum != 0)
            else:
                results["mean"] = data.mean(dim=dim, skipna=True)

        if "std" in stats:
            results["std"] = data.std(dim=dim, skipna=True)

        if "min" in stats:
            results["min"] = data.min(dim=dim, skipna=True)

        if "max" in stats:
            results["max"] = data.max(dim=dim, skipna=True)

        if "median" in stats:
            results["median"] = data.median(dim=dim, skipna=True)

        if "count" in stats:
            results["count"] = data.notnull().sum(dim=dim)

        # Estatísticas adicionais
        if "q25" in stats:
            results["q25"] = data.quantile(0.25, dim=dim, skipna=True)

        if "q75" in stats:
            results["q75"] = data.quantile(0.75, dim=dim, skipna=True)

        if "iqr" in stats:
            q75 = data.quantile(0.75, dim=dim, skipna=True)
            q25 = data.quantile(0.25, dim=dim, skipna=True)
            results["iqr"] = q75 - q25

        if "skew" in stats:
            results["skew"] = self._calculate_skewness(data, dim)

        if "kurtosis" in stats:
            results["kurtosis"] = self._calculate_kurtosis(data, dim)

        # Converter para float se resultado for escalar
        for key, value in results.items():
            if isinstance(value, xr.DataArray) and value.size == 1:
                results[key] = float(value)

        return results

    def _calculate_skewness(
        self, data: xr.DataArray, dim: str | list[str] | None
    ) -> float | xr.DataArray:
        """Calcula assimetria (skewness) dos dados."""
        mean = data.mean(dim=dim, skipna=True)
        std = data.std(dim=dim, skipna=True)

        # Momento centralizado de ordem 3
        centered = data - mean
        m3 = (centered**3).mean(dim=dim, skipna=True)

        return m3 / (std**3).where(std != 0)

    def _calculate_kurtosis(
        self, data: xr.DataArray, dim: str | list[str] | None
    ) -> float | xr.DataArray:
        """Calcula curtose (kurtosis) dos dados."""
        mean = data.mean(dim=dim, skipna=True)
        std = data.std(dim=dim, skipna=True)

        # Momento centralizado de ordem 4
        centered = data - mean
        m4 = (centered**4).mean(dim=dim, skipna=True)

        return (m4 / (std**4).where(std != 0)) - 3  # Excess kurtosis

    def export_zcit_line(
        self,
        coordinates: list[Coordinate],
        output_path: PathLike,
        format: str = "geojson",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Exporta linha da ZCIT para arquivo.

        Como "desenhar o mapa do tesouro" mostrando onde a ZCIT
        foi encontrada, em formato que outros programas entendam.

        Parameters
        ----------
        coordinates : List[Tuple[float, float]]
            Lista de coordenadas (lon, lat) da ZCIT
        output_path : str or Path
            Caminho do arquivo de saída
        format : str, default "geojson"
            Formato: "geojson", "shapefile", "csv", "json"
        metadata : dict, optional
            Metadados adicionais para incluir
        """
        if not coordinates:
            logger.warning("Lista de coordenadas vazia. Nada a exportar.")
            return

        output_path = Path(output_path)
        logger.info(
            f"Exportando {len(coordinates)} pontos da ZCIT "
            f"para {output_path} (formato: {format})"
        )

        if format == "geojson":
            self._export_geojson(coordinates, output_path, metadata)
        elif format == "shapefile":
            self._export_shapefile(coordinates, output_path, metadata)
        elif format == "csv":
            self._export_csv(coordinates, output_path, metadata)
        elif format == "json":
            self._export_json(coordinates, output_path, metadata)
        else:
            raise ValueError(
                f"Formato '{format}' não suportado. Use: geojson, shapefile, csv, json"
            )

        logger.info(f"Exportação concluída: {output_path}")

    def _export_geojson(
        self,
        coordinates: list[Coordinate],
        output_path: Path,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Exporta para formato GeoJSON."""
        import json

        features = []
        for i, (lon, lat) in enumerate(coordinates):
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "index": i,
                    "longitude": lon,
                    "latitude": lat,
                },
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features,
            "metadata": metadata or {},
        }

        with open(output_path, "w") as f:
            json.dump(geojson, f, indent=2)

    def _export_shapefile(
        self,
        coordinates: list[Coordinate],
        output_path: Path,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Exporta para formato Shapefile."""
        if not HAS_GEOPANDAS:
            raise ImportError("GeoPandas necessário para exportar Shapefile")

        from shapely.geometry import Point

        # Criar GeoDataFrame
        geometry = [Point(lon, lat) for lon, lat in coordinates]
        gdf = gpd.GeoDataFrame(
            {
                "longitude": [c[0] for c in coordinates],
                "latitude": [c[1] for c in coordinates],
            },
            geometry=geometry,
            crs="EPSG:4326",
        )

        # Adicionar metadados como atributos se possível
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (str, int, float)):
                    gdf[key] = value

        gdf.to_file(output_path, driver="ESRI Shapefile")

    def _export_csv(
        self,
        coordinates: list[Coordinate],
        output_path: Path,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Exporta para formato CSV."""
        import csv

        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)

            # Escrever metadados como comentários
            if metadata:
                for key, value in metadata.items():
                    writer.writerow([f"# {key}: {value}"])

            # Escrever cabeçalho e dados
            writer.writerow(["longitude", "latitude"])
            writer.writerows(coordinates)

    def _export_json(
        self,
        coordinates: list[Coordinate],
        output_path: Path,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Exporta para formato JSON."""
        import json

        data = {
            "coordinates": [
                {"longitude": lon, "latitude": lat} for lon, lat in coordinates
            ],
            "metadata": metadata or {},
            "count": len(coordinates),
        }

        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def quality_control(
        self,
        data: xr.Dataset,
        checks: list[str] | None = None,
        fix: bool = False,
    ) -> tuple[xr.Dataset, dict[str, Any]]:
        """
        Realiza controle de qualidade nos dados.

        Como um "médico" que examina os dados, diagnostica problemas
        e, opcionalmente, aplica tratamentos.

        Parameters
        ----------
        data : xr.Dataset
            Dados para verificar
        checks : list, optional
            Verificações específicas. Se None, faz todas
        fix : bool, default False
            Se True, tenta corrigir problemas encontrados

        Returns
        -------
        xr.Dataset
            Dados (possivelmente corrigidos)
        Dict[str, Any]
            Relatório com problemas encontrados
        """
        if checks is None:
            checks = [
                "missing_coords",
                "invalid_values",
                "time_gaps",
                "spatial_coverage",
                "data_range",
            ]

        logger.info(
            f"Iniciando controle de qualidade "
            f"(verificações: {len(checks)}, corrigir: {fix})"
        )

        report = {"checks_performed": checks, "issues": {}}
        data_fixed = data.copy(deep=True) if fix else data

        # Executar verificações
        for check in checks:
            if check == "missing_coords":
                issues = self._check_missing_coords(data_fixed)
                if issues and fix:
                    data_fixed = self._fix_missing_coords(data_fixed)

            elif check == "invalid_values":
                issues = self._check_invalid_values(data_fixed)
                if issues and fix:
                    data_fixed = self._fix_invalid_values(data_fixed)

            elif check == "time_gaps":
                issues = self._check_time_gaps(data_fixed)
                if issues and fix:
                    data_fixed = self._fix_time_gaps(data_fixed)

            elif check == "spatial_coverage":
                issues = self._check_spatial_coverage(data_fixed)

            elif check == "data_range":
                issues = self._check_data_range(data_fixed)
                if issues and fix:
                    data_fixed = self._fix_data_range(data_fixed)

            else:
                logger.warning(f"Verificação '{check}' não reconhecida")
                continue

            if issues:
                report["issues"][check] = issues

        # Resumo
        total_issues = sum(
            len(v) if isinstance(v, list) else 1 for v in report["issues"].values()
        )
        report["summary"] = {
            "total_issues": total_issues,
            "data_modified": fix and total_issues > 0,
        }

        logger.info(
            f"Controle de qualidade concluído: {total_issues} problemas encontrados"
        )

        return data_fixed, report

    def _check_missing_coords(self, data: xr.Dataset) -> list[str]:
        """Verifica coordenadas faltantes."""
        required_coords = ["lat", "lon", "time"]
        missing = [c for c in required_coords if c not in data.coords]
        return missing

    def _fix_missing_coords(self, data: xr.Dataset) -> xr.Dataset:
        """Tenta adicionar coordenadas faltantes."""
        # Implementação simplificada - em produção seria mais robusta
        logger.warning("Correção automática de coordenadas não implementada")
        return data

    def _check_invalid_values(self, data: xr.Dataset) -> dict[str, int]:
        """Verifica valores inválidos (NaN, Inf)."""
        issues = {}

        for var in data.data_vars:
            array = data[var]
            nan_count = int(array.isnull().sum())
            inf_count = int(np.isinf(array).sum())

            if nan_count > 0:
                issues[f"{var}_nan"] = nan_count
            if inf_count > 0:
                issues[f"{var}_inf"] = inf_count

        return issues

    def _fix_invalid_values(self, data: xr.Dataset) -> xr.Dataset:
        """Remove ou corrige valores inválidos."""
        for var in data.data_vars:
            # Substituir Inf por NaN
            data[var] = data[var].where(~np.isinf(data[var]))

        return data

    def _check_time_gaps(self, data: xr.Dataset) -> list[str]:
        """Verifica gaps na série temporal."""
        if "time" not in data.coords:
            return ["coordenada time não encontrada"]

        issues = []
        time_diff = np.diff(data.time.values)

        # Assumir que a diferença modal é o intervalo esperado
        if len(time_diff) > 0:
            expected_diff = stats.mode(time_diff).mode
            gaps = np.where(time_diff > expected_diff * 1.5)[0]

            for gap_idx in gaps:
                issues.append(f"Gap entre índices {gap_idx} e {gap_idx + 1}")

        return issues

    def _fix_time_gaps(self, data: xr.Dataset) -> xr.Dataset:
        """Preenche gaps temporais via interpolação."""
        # Implementação simplificada
        logger.warning("Correção automática de gaps temporais não implementada")
        return data

    def _check_spatial_coverage(self, data: xr.Dataset) -> dict[str, float]:
        """Verifica cobertura espacial dos dados."""
        if "lat" not in data.coords or "lon" not in data.coords:
            return {"error": "coordenadas espaciais não encontradas"}

        # Calcular porcentagem de cobertura para cada variável
        coverage = {}

        for var in data.data_vars:
            if "lat" in data[var].dims and "lon" in data[var].dims:
                valid_ratio = float(
                    data[var].notnull().any(dim="time").mean()
                    if "time" in data[var].dims
                    else data[var].notnull().mean()
                )
                coverage[var] = valid_ratio * 100

        return coverage

    def _check_data_range(self, data: xr.Dataset) -> dict[str, dict[str, float]]:
        """Verifica se valores estão em faixas esperadas."""
        issues = {}

        # Faixas esperadas para variáveis comuns
        expected_ranges = {
            "olr": (50.0, 450.0),
            "temperature": (-100.0, 100.0),
            "precipitation": (0.0, 1000.0),
        }

        for var in data.data_vars:
            if var in expected_ranges:
                min_val = float(data[var].min(skipna=True))
                max_val = float(data[var].max(skipna=True))
                expected_min, expected_max = expected_ranges[var]

                if min_val < expected_min or max_val > expected_max:
                    issues[var] = {
                        "min": min_val,
                        "max": max_val,
                        "expected_min": expected_min,
                        "expected_max": expected_max,
                    }

        return issues

    def _fix_data_range(self, data: xr.Dataset) -> xr.Dataset:
        """Aplica clipping aos valores fora da faixa."""
        expected_ranges = {
            "olr": (50.0, 450.0),
            "temperature": (-100.0, 100.0),
            "precipitation": (0.0, 1000.0),
        }

        for var in data.data_vars:
            if var in expected_ranges:
                min_val, max_val = expected_ranges[var]
                data[var] = data[var].clip(min=min_val, max=max_val)
                logger.info(f"Valores de '{var}' limitados a [{min_val}, {max_val}]")

        return data

    def calculate_dual_scale_statistics(
        self,
        dados_globais: xr.Dataset,
        dados_study_area: xr.Dataset,
        variable: str = "olr",
    ) -> dict[str, dict[str, float]]:
        """
        Calcula estatísticas comparativas entre dados globais e study area.

        ANALOGIA DO MÉDICO COMPARATIVO 🏥
        É como um médico que:
        1. Examina a saúde geral do paciente (dados globais)
        2. Foca em um órgão específico (study area)
        3. Compara os resultados para diagnóstico preciso

        Parameters
        ----------
        dados_globais : xr.Dataset
            Dataset com dados globais
        dados_study_area : xr.Dataset
            Dataset com dados da study area
        variable : str, default 'olr'
            Variável para calcular estatísticas

        Returns
        -------
        Dict[str, Dict[str, float]]
            Estatísticas organizadas por escala
        """

        logger.info(f"📊 Calculando estatísticas comparativas para '{variable}'...")

        if variable not in dados_globais or variable not in dados_study_area:
            raise ValueError(f"Variável '{variable}' não encontrada nos datasets")

        # Calcular estatísticas globais
        stats_globais = {
            "media": float(dados_globais[variable].mean()),
            "mediana": float(dados_globais[variable].median()),
            "desvio_padrao": float(dados_globais[variable].std()),
            "minimo": float(dados_globais[variable].min()),
            "maximo": float(dados_globais[variable].max()),
            "q25": float(dados_globais[variable].quantile(0.25)),
            "q75": float(dados_globais[variable].quantile(0.75)),
            "pixels_totais": int(dados_globais[variable].size),
            "pixels_validos": int(dados_globais[variable].notnull().sum()),
            "area_tipo": "global",
        }

        # Calcular estatísticas da study area
        stats_study_area = {
            "media": float(dados_study_area[variable].mean()),
            "mediana": float(dados_study_area[variable].median()),
            "desvio_padrao": float(dados_study_area[variable].std()),
            "minimo": float(dados_study_area[variable].min()),
            "maximo": float(dados_study_area[variable].max()),
            "q25": float(dados_study_area[variable].quantile(0.25)),
            "q75": float(dados_study_area[variable].quantile(0.75)),
            "pixels_totais": int(dados_study_area[variable].size),
            "pixels_validos": int(dados_study_area[variable].notnull().sum()),
            "area_tipo": "study_area",
        }

        # Calcular diferenças e razões
        diferenca_media = stats_study_area["media"] - stats_globais["media"]
        diferenca_desvio = (
            stats_study_area["desvio_padrao"] - stats_globais["desvio_padrao"]
        )

        # Calcular representatividade
        representatividade = (
            stats_study_area["pixels_totais"] / stats_globais["pixels_totais"]
        ) * 100

        stats_comparativas = {
            "diferenca_media": diferenca_media,
            "diferenca_desvio": diferenca_desvio,
            "razao_medias": stats_study_area["media"] / stats_globais["media"]
            if stats_globais["media"] != 0
            else np.nan,
            "representatividade_percentual": representatividade,
            "interpretacao": self._interpretar_diferenca_estatistica(
                diferenca_media, variable
            ),
        }

        logger.info(f"📈 Diferença nas médias: {diferenca_media:+.1f} W/m²")
        logger.info(f"📊 Study area representa: {representatividade:.1f}% dos dados")
        logger.info(f"📊 {stats_comparativas['interpretacao']}")

        return {
            "global": stats_globais,
            "study_area": stats_study_area,
            "comparacao": stats_comparativas,
        }

    def _interpretar_diferenca_estatistica(
        self, diferenca: float, variable: str
    ) -> str:
        """
        Interpreta a diferença estatística entre global e study area.

        ANALOGIA DO TRADUTOR 🌐
        Como um tradutor que converte números em linguagem compreensível,
        explicando o que as diferenças realmente significam.
        """

        if variable.lower() == "olr":
            if abs(diferenca) < 5:
                return "Study area similar ao padrão global (diferença < 5 W/m²)"
            if diferenca < -5:
                return "Study area com MAIS atividade convectiva (OLR menor que global)"
            return "Study area com MENOS atividade convectiva (OLR maior que global)"
        if abs(diferenca) < 0.1:
            return "Study area muito similar ao padrão global"
        if diferenca > 0:
            return "Study area com valores MAIORES que a média global"
        return "Study area com valores MENORES que a média global"

    def find_minimum_coordinates_dual_scale(
        self,
        dados_globais: xr.DataArray,
        dados_study_area: xr.DataArray | None = None,
        use_global_context: bool = True,
        **kwargs,
    ) -> list[tuple[float, float]]:
        """
        Encontra coordenadas mínimas usando estratégia dupla escala.

        ANALOGIA DO EXPLORADOR ESTRATÉGICO 🗺️
        É como um explorador que:
        1. Usa mapa geral para orientação (dados globais)
        2. Foca na região de interesse (study area)
        3. Encontra tesouros com contexto completo

        Parameters
        ----------
        dados_globais : xr.DataArray
            Dados globais para contexto
        dados_study_area : xr.DataArray, optional
            Dados da study area para busca focada
        use_global_context : bool, default True
            Se True, usa dados globais. Se False, usa study area
        **kwargs
            Argumentos para find_minimum_coordinates

        Returns
        -------
        List[Tuple[float, float]]
            Coordenadas dos mínimos encontrados
        """

        logger.info(
            f"🔍 Buscando mínimos (contexto: {'global' if use_global_context else 'study_area'})..."
        )

        # Escolher dados baseado na estratégia
        if use_global_context or dados_study_area is None:
            dados_para_busca = dados_globais
            logger.info("Usando dados globais para busca (contexto completo)")
        else:
            dados_para_busca = dados_study_area
            logger.info("Usando dados da study area para busca (contexto focado)")

        # Usar método existente
        coordenadas = self.find_minimum_coordinates(dados_para_busca, **kwargs)

        logger.info(f"✅ Encontradas {len(coordenadas)} coordenadas")

        return coordenadas

    def __repr__(self) -> str:
        """Representação textual do processador."""
        cache_info = f"{len(self._pentads_cache)}/{self._pentads_cache_size}"
        return (
            f"<DataProcessor("
            f"use_dask={self.use_dask}, "
            f"n_workers={self.n_workers}, "
            f"cache={cache_info}, "
            f"default_area={'✓' if self.default_study_area_path else '✗'}"
            f")>"
        )
