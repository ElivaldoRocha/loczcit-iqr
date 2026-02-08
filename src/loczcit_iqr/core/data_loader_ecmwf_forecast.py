"""
data_loader_ecmwf_forecast.py
==============================

Módulo para download de PREVISÃO de OLR do ECMWF IFS.

Este módulo baixa dados de previsão de radiação térmica (OLR/TTR) do modelo
operacional ECMWF IFS, permitindo prever a posição da ZCIT até 15 dias no futuro.

IMPORTANTE - Conversão de Unidades:
===================================
O TTR (Top Net Thermal Radiation) do ECMWF IFS Open Data é:
- Acumulado desde o início do forecast (step=0)
- Unidade: J/m² (Joules por metro quadrado)
- Convenção de sinal: NEGATIVO = radiação saindo (OLR)

Para obter OLR médio de um PERÍODO ESPECÍFICO (ex: dia 3 ao dia 4):
- Calcular a DIFERENÇA entre dois steps consecutivos
- Dividir pelo período em segundos
- Inverter o sinal

Referências:
- ECMWF Open Data: https://www.ecmwf.int/en/forecasts/datasets/open-data
- TTR Parameter: https://codes.ecmwf.int/grib/param-db/?id=179
- Radiation in ECMWF: https://www.ecmwf.int/sites/default/files/elibrary/2015/18490-radiation-quantities-ecmwf-model-and-mars.pdf
- Conversão: https://confluence.ecmwf.int/pages/viewpage.action?pageId=155337784

Author: LOCZCIT-IQR Development Team
License: MIT
"""

from __future__ import annotations

import logging
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import xarray as xr

# Logger
logger = logging.getLogger(__name__)

# Tentar importar dependências
try:
    from ecmwf.opendata import Client as ECMWFClient
    HAS_ECMWF_OPENDATA = True
except ImportError:
    HAS_ECMWF_OPENDATA = False
    ECMWFClient = None
    warnings.warn(
        "ecmwf-opendata não instalado. Instale com: pip install ecmwf-opendata",
        ImportWarning
    )

try:
    import cfgrib
    HAS_CFGRIB = True
except ImportError:
    HAS_CFGRIB = False
    warnings.warn(
        "cfgrib não instalado. Instale com: pip install cfgrib eccodes",
        ImportWarning
    )


class ECMWFForecastLoader:
    """
    Loader para PREVISÃO de OLR do ECMWF IFS.
    
    Esta classe baixa dados de previsão do modelo operacional ECMWF IFS,
    permitindo analisar a posição FUTURA da ZCIT.
    
    A saída é 100% compatível com o formato do ERA5DataLoader e NOAADataLoader,
    permitindo uso direto com o DataProcessor da LOCZCIT-IQR.
    
    Workflow Científico:
    --------------------
    1. O IFS fornece TTR acumulado desde step=0 em J/m²
    2. Para obter OLR médio em W/m² para um período, usamos:
       OLR = (TTR[step_final] - TTR[step_inicial]) / (segundos do período) * (-1)
    3. Para previsões de pentada (5 dias), calculamos a média de OLR diária
    
    Attributes
    ----------
    cache_dir : Path
        Diretório para cache dos arquivos GRIB
    source : str
        Fonte dos dados: 'ecmwf', 'aws', 'azure', 'google'
    
    Examples
    --------
    >>> loader = ECMWFForecastLoader()
    >>> 
    >>> # Previsão para os próximos 5 dias
    >>> forecast = loader.load_forecast(forecast_days=5)
    >>> print(forecast.olr.mean())
    >>> 
    >>> # Usar diretamente com LOCZCIT-IQR
    >>> from loczcit_iqr.core.processor import DataProcessor
    >>> processor = DataProcessor()
    >>> min_coords = processor.find_minimum_coordinates(forecast.olr)
    """
    
    # Constantes
    VARIABLE_TTR = "ttr"  # Top net thermal radiation (OLR)
    
    # Área padrão da ZCIT (igual ao ERA5DataLoader e NOAADataLoader)
    DEFAULT_AREA = (17, -80, -12, 4)  # (lat_norte, lon_oeste, lat_sul, lon_leste)
    
    # Limites válidos de OLR (igual ao ERA5DataLoader)
    OLR_VALID_RANGE = (50.0, 450.0)
    
    # Steps disponíveis (em horas)
    # 00z/12z: 0-144 by 3h, 150-360 by 6h
    AVAILABLE_STEPS_00_12 = list(range(0, 145, 3)) + list(range(150, 361, 6))
    # 06z/18z: 0-144 by 3h
    AVAILABLE_STEPS_06_18 = list(range(0, 145, 3))
    
    def __init__(
        self,
        cache_dir: str | Path = "./ecmwf_forecast_cache",
        source: str = "aws",  # aws é mais estável
        log_level: int | str = logging.INFO,
    ):
        """
        Inicializa o loader de previsões ECMWF.
        
        Parameters
        ----------
        cache_dir : str or Path
            Diretório para cache de arquivos GRIB
        source : str
            Fonte dos dados: 'ecmwf', 'aws', 'azure', 'google'
            Recomendado: 'aws' (mais estável e sem limite de conexões)
        log_level : int or str
            Nível de logging
        """
        self._setup_logging(log_level)
        self._check_dependencies()
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.source = source
        
        # Cliente ECMWF (lazy loading)
        self._client = None
        
        logger.info(f"ECMWFForecastLoader inicializado (source: {source})")
    
    def _setup_logging(self, level: int | str) -> None:
        """Configura logging."""
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(level)
    
    def _check_dependencies(self) -> None:
        """Verifica dependências necessárias."""
        if not HAS_ECMWF_OPENDATA:
            raise ImportError(
                "ecmwf-opendata não instalado!\n"
                "Instale com: pip install ecmwf-opendata"
            )
        if not HAS_CFGRIB:
            raise ImportError(
                "cfgrib não instalado!\n"
                "Instale com: pip install cfgrib eccodes"
            )
    
    @property
    def client(self) -> ECMWFClient:
        """Cliente ECMWF (inicializado sob demanda)."""
        if self._client is None:
            self._client = ECMWFClient(
                source=self.source,
                model="ifs",
                resol="0p25",
                infer_stream_keyword=True,
            )
            logger.info(f"Cliente ECMWF inicializado (source: {self.source})")
        return self._client
    
    def get_latest_forecast_time(self) -> Tuple[datetime, int]:
        """
        Obtém a hora da última previsão disponível.
        
        Returns
        -------
        tuple
            (datetime da rodada, hora UTC)
        """
        now = datetime.utcnow()
        run_hours = [0, 6, 12, 18]
        lag_hours = 3  # Lag de disponibilidade
        
        available_time = now - timedelta(hours=lag_hours)
        valid_hours = [h for h in run_hours if h <= available_time.hour]
        
        if valid_hours:
            run_hour = max(valid_hours)
            run_date = available_time.date()
        else:
            run_date = available_time.date() - timedelta(days=1)
            run_hour = 18
        
        forecast_time = datetime.combine(
            run_date, 
            datetime.min.time().replace(hour=run_hour)
        )
        
        return forecast_time, run_hour
    
    def _get_available_steps(self, run_hour: int) -> List[int]:
        """Retorna steps disponíveis para a rodada."""
        if run_hour in [0, 12]:
            return self.AVAILABLE_STEPS_00_12
        else:
            return self.AVAILABLE_STEPS_06_18
    
    def _get_cache_filename(self, run_time: datetime, step: int) -> Path:
        """Gera nome de arquivo para cache."""
        return self.cache_dir / f"ecmwf_ifs_{run_time.strftime('%Y%m%d%H')}_{step:03d}h.grib2"
    
    def _download_step(
        self,
        run_time: datetime,
        step: int,
        cache_file: Path,
    ) -> xr.Dataset:
        """Baixa um step de previsão."""
        try:
            logger.debug(f"Baixando TTR: {run_time.strftime('%Y%m%d')} {run_time.hour:02d}z step={step}")
            
            self.client.retrieve(
                date=run_time.strftime("%Y%m%d"),
                time=run_time.hour,
                step=step,
                param=self.VARIABLE_TTR,
                target=str(cache_file),
            )
            
            logger.info(f"Download concluído: {cache_file.name}")
            return self._load_grib_file(cache_file)
            
        except Exception as e:
            logger.error(f"Erro no download: {e}")
            raise
    
    def _load_grib_file(self, filepath: Path) -> xr.Dataset:
        """Carrega arquivo GRIB com cfgrib."""
        return xr.open_dataset(filepath, engine="cfgrib")
    
    def _get_ttr_for_step(
        self,
        run_time: datetime,
        step: int,
        area: Tuple[float, float, float, float] | None,
    ) -> xr.Dataset:
        """Obtém dados TTR para um step específico."""
        cache_file = self._get_cache_filename(run_time, step)
        
        if cache_file.exists():
            logger.debug(f"Usando cache: {cache_file.name}")
            ds = self._load_grib_file(cache_file)
        else:
            ds = self._download_step(run_time, step, cache_file)
        
        # Recortar área se especificada
        if area is not None:
            ds = self._crop_area(ds, area)
        
        return ds
    
    def _crop_area(
        self,
        ds: xr.Dataset,
        area: Tuple[float, float, float, float],
    ) -> xr.Dataset:
        """Recorta área do dataset."""
        lat_max, lon_min, lat_min, lon_max = area
        
        lat_name = "latitude" if "latitude" in ds.coords else "lat"
        lon_name = "longitude" if "longitude" in ds.coords else "lon"
        
        lon_vals = ds[lon_name].values
        
        # Ajustar longitude para formato ECMWF (0-360)
        if lon_vals.min() >= 0 and lon_vals.max() <= 360:
            if lon_min < 0:
                lon_min_adj = lon_min + 360
            else:
                lon_min_adj = lon_min
            if lon_max < 0:
                lon_max_adj = lon_max + 360
            else:
                lon_max_adj = lon_max
        else:
            lon_min_adj = lon_min
            lon_max_adj = lon_max
        
        ds = ds.sel(**{
            lat_name: slice(lat_max, lat_min),
            lon_name: slice(lon_min_adj, lon_max_adj)
        })
        
        return ds
    
    def load_forecast_daily_mean(
        self,
        day: int,
        run_time: datetime | None = None,
        area: Tuple[float, float, float, float] | None = None,
    ) -> xr.Dataset:
        """
        Carrega OLR médio diário previsto para um dia específico.
        
        Este método calcula corretamente o OLR médio diário usando a
        diferença entre dois steps consecutivos de 24h.
        
        Fórmula científica:
        OLR_dia_N = (TTR[step_24N] - TTR[step_24(N-1)]) / 86400 * (-1)
        
        Parameters
        ----------
        day : int
            Dia da previsão (1 = amanhã, 2 = depois de amanhã, etc.)
        run_time : datetime, optional
            Data/hora da rodada
        area : tuple, optional
            Área de estudo
        
        Returns
        -------
        xr.Dataset
            OLR médio diário no formato NOAA
        """
        if day < 1:
            raise ValueError("day deve ser >= 1")
        
        if run_time is None:
            run_time, run_hour = self.get_latest_forecast_time()
        else:
            run_hour = run_time.hour
        
        study_area = area or self.DEFAULT_AREA
        
        # Para calcular média diária do dia N:
        # step_fim = 24 * N (ex: dia 1 = step 24, dia 2 = step 48)
        # step_inicio = 24 * (N-1) (ex: dia 1 = step 0, dia 2 = step 24)
        step_end = day * 24
        step_start = (day - 1) * 24
        
        # Verificar disponibilidade de steps
        available = self._get_available_steps(run_hour)
        
        # Encontrar steps mais próximos
        step_end_actual = min(available, key=lambda x: abs(x - step_end))
        step_start_actual = min(available, key=lambda x: abs(x - step_start))
        
        if step_end_actual <= step_start_actual:
            raise ValueError(
                f"Steps inválidos: {step_start_actual} -> {step_end_actual}"
            )
        
        logger.info(
            f"Calculando OLR dia {day}: steps {step_start_actual}h -> {step_end_actual}h"
        )
        
        # Obter dados TTR para ambos os steps
        ttr_end = self._get_ttr_for_step(run_time, step_end_actual, study_area)
        
        if step_start_actual == 0:
            # Para step=0, TTR é zero (início do forecast)
            ttr_start_values = 0
        else:
            ttr_start = self._get_ttr_for_step(run_time, step_start_actual, study_area)
            ttr_start_values = self._extract_ttr_values(ttr_start)
        
        ttr_end_values = self._extract_ttr_values(ttr_end)
        
        # Calcular diferença e converter
        delta_seconds = (step_end_actual - step_start_actual) * 3600
        
        # OLR = (TTR_fim - TTR_inicio) / delta_segundos * (-1)
        olr_values = (ttr_end_values - ttr_start_values) / delta_seconds * (-1)
        
        # Garantir valores positivos
        olr_values = np.abs(olr_values)
        
        # Data válida (centro do período)
        valid_time = run_time + timedelta(hours=(step_start_actual + step_end_actual) / 2)
        
        # Criar dataset no formato NOAA
        ds_out = self._create_noaa_format_dataset(
            olr_values=olr_values,
            ds_template=ttr_end,
            valid_time=valid_time,
            run_time=run_time,
            step_info=f"{step_start_actual}-{step_end_actual}h"
        )
        
        return ds_out
    
    def load_forecast(
        self,
        forecast_days: int = 5,
        run_time: datetime | None = None,
        area: Tuple[float, float, float, float] | None = None,
        aggregate: str = "mean",
    ) -> xr.Dataset:
        """
        Carrega previsão de OLR para múltiplos dias e agrega.
        
        Esta é a função principal para análise ZCIT - ela calcula
        o OLR médio para cada dia de previsão e depois agrega.
        
        Parameters
        ----------
        forecast_days : int
            Número de dias de previsão (1-15)
        run_time : datetime, optional
            Data/hora da rodada
        area : tuple, optional
            Área de estudo
        aggregate : str
            Método de agregação: 'mean', 'median', 'min', 'max'
        
        Returns
        -------
        xr.Dataset
            Dados de OLR agregados no formato NOAA
        """
        if forecast_days < 1 or forecast_days > 15:
            raise ValueError("forecast_days deve ser entre 1 e 15")
        
        if run_time is None:
            run_time, _ = self.get_latest_forecast_time()
        
        study_area = area or self.DEFAULT_AREA
        
        logger.info(f"Carregando previsão de OLR para {forecast_days} dias")
        
        # Carregar OLR diário para cada dia
        daily_datasets = []
        for day in range(1, forecast_days + 1):
            try:
                ds_day = self.load_forecast_daily_mean(day, run_time, study_area)
                daily_datasets.append(ds_day)
                logger.info(f"  Dia {day}: OLR médio = {ds_day.olr.mean().values:.2f} W/m²")
            except Exception as e:
                logger.warning(f"  Dia {day}: Erro - {e}")
                continue
        
        if not daily_datasets:
            raise RuntimeError("Nenhum dado de previsão carregado")
        
        # Concatenar ao longo do tempo
        combined = xr.concat(daily_datasets, dim="time")
        
        # Aplicar agregação
        agg_func = {
            "mean": lambda x: x.mean(dim="time"),
            "median": lambda x: x.median(dim="time"),
            "min": lambda x: x.min(dim="time"),
            "max": lambda x: x.max(dim="time"),
        }
        
        if aggregate not in agg_func:
            raise ValueError(f"aggregate deve ser: {list(agg_func.keys())}")
        
        olr_agg = agg_func[aggregate](combined["olr"])
        
        # Criar dataset de saída
        ds_out = xr.Dataset({"olr": olr_agg})
        
        # Metadados
        ds_out["olr"].attrs = {
            "long_name": f"Outgoing Longwave Radiation ({aggregate} forecast)",
            "standard_name": "toa_outgoing_longwave_flux",
            "units": "W m**-2",
            "cell_methods": f"time: {aggregate}",
            "valid_min": self.OLR_VALID_RANGE[0],
            "valid_max": self.OLR_VALID_RANGE[1],
            "source": "ECMWF IFS Operational Forecast",
            "original_variable": "top_net_thermal_radiation",
            "conversion_formula": "(TTR[step_fim] - TTR[step_inicio]) / delta_seconds * (-1)",
            "comment": "Converted from ECMWF IFS format to NOAA OLR CDR format",
        }
        
        ds_out.attrs = {
            "title": f"ECMWF IFS OLR Forecast ({aggregate}) - NOAA-compatible",
            "institution": "European Centre for Medium-Range Weather Forecasts (ECMWF)",
            "source": "ECMWF IFS Operational Forecast",
            "forecast_run": run_time.isoformat(),
            "forecast_days": forecast_days,
            "aggregation_method": aggregate,
            "history": f"Created on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "conventions": "CF-1.7",
            "spatial_resolution": "0.25 degrees",
            "converted_for": "loczcit_iqr library compatibility",
        }
        
        # Atributos das coordenadas
        if "lat" in ds_out.coords:
            ds_out["lat"].attrs = {
                "long_name": "latitude",
                "standard_name": "latitude",
                "units": "degrees_north",
                "axis": "Y",
            }
        
        if "lon" in ds_out.coords:
            ds_out["lon"].attrs = {
                "long_name": "longitude",
                "standard_name": "longitude",
                "units": "degrees_east",
                "axis": "X",
            }
        
        logger.info(
            f"Previsão carregada: {len(daily_datasets)} dias, "
            f"OLR médio = {ds_out.olr.mean().values:.2f} W/m²"
        )
        
        return ds_out
    
    def _extract_ttr_values(self, ds: xr.Dataset) -> np.ndarray:
        """Extrai valores TTR do dataset."""
        for name in ["ttr", "tisr", "str"]:
            if name in ds.data_vars:
                return ds[name].values
        
        # Usar primeira variável
        var_name = list(ds.data_vars)[0]
        logger.warning(f"TTR não encontrado, usando: {var_name}")
        return ds[var_name].values
    
    def _create_noaa_format_dataset(
        self,
        olr_values: np.ndarray,
        ds_template: xr.Dataset,
        valid_time: datetime,
        run_time: datetime,
        step_info: str,
    ) -> xr.Dataset:
        """
        Cria dataset no formato NOAA compatível com LOCZCIT-IQR.
        
        Esta função replica exatamente a estrutura do ERA5DataLoader._convert_to_noaa_format()
        """
        # ================================================================
        # 1. REMOVER COORDENADAS EXTRAS
        # ================================================================
        # Verificar coordenadas do template
        for coord_name in ["number", "step", "valid_time", "surface"]:
            if coord_name in ds_template.dims:
                ds_template = ds_template.squeeze(coord_name, drop=True)
            if coord_name in ds_template.coords:
                try:
                    ds_template = ds_template.drop_vars(coord_name)
                except:
                    pass
        
        # ================================================================
        # 2. EXTRAIR E PROCESSAR COORDENADAS
        # ================================================================
        # Latitude
        if "latitude" in ds_template.coords:
            lat_values = ds_template.latitude.values
        elif "lat" in ds_template.coords:
            lat_values = ds_template.lat.values
        else:
            raise ValueError("Coordenada latitude não encontrada")
        
        # Garantir ordem Norte → Sul (como NOAA)
        if lat_values[0] < lat_values[-1]:
            lat_values = lat_values[::-1]
            olr_values = olr_values[..., ::-1, :]
        
        # Longitude
        if "longitude" in ds_template.coords:
            lon_values = ds_template.longitude.values
        elif "lon" in ds_template.coords:
            lon_values = ds_template.lon.values
        else:
            raise ValueError("Coordenada longitude não encontrada")
        
        # Converter 0-360 → -180-180 (como NOAA)
        if lon_values.max() > 180:
            lon_converted = np.where(lon_values > 180, lon_values - 360, lon_values)
            sort_idx = np.argsort(lon_converted)
            lon_values = lon_converted[sort_idx]
            olr_values = olr_values[..., sort_idx]
        
        # ================================================================
        # 3. CRIAR COORDENADA TEMPORAL
        # ================================================================
        # CRÍTICO: Usar datetime64[ns] para compatibilidade com processor.py
        time_ns = pd.DatetimeIndex([valid_time]).values
        
        # ================================================================
        # 4. GARANTIR SHAPE (time, lat, lon)
        # ================================================================
        if olr_values.ndim == 2:
            olr_values = olr_values[np.newaxis, ...]
        
        # ================================================================
        # 5. CRIAR DATASET
        # ================================================================
        olr_da = xr.DataArray(
            data=olr_values,
            dims=["time", "lat", "lon"],
            coords={
                "time": time_ns,
                "lat": lat_values,
                "lon": lon_values,
            },
            name="olr",
            attrs={
                "long_name": "Outgoing Longwave Radiation (Forecast)",
                "standard_name": "toa_outgoing_longwave_flux",
                "units": "W m**-2",
                "valid_min": self.OLR_VALID_RANGE[0],
                "valid_max": self.OLR_VALID_RANGE[1],
                "source": "ECMWF IFS Forecast",
                "forecast_run": run_time.isoformat(),
                "forecast_steps": step_info,
                "valid_time": valid_time.isoformat(),
            }
        )
        
        # Atributos das coordenadas (IDÊNTICO ao ERA5DataLoader)
        olr_da["lat"].attrs = {
            "long_name": "latitude",
            "standard_name": "latitude",
            "units": "degrees_north",
            "axis": "Y",
        }
        
        olr_da["lon"].attrs = {
            "long_name": "longitude",
            "standard_name": "longitude",
            "units": "degrees_east",
            "axis": "X",
        }
        
        olr_da["time"].attrs = {
            "long_name": "time",
            "standard_name": "time",
            "axis": "T",
        }
        
        ds_out = xr.Dataset({"olr": olr_da})
        ds_out.attrs = {
            "title": "ECMWF IFS OLR Forecast (NOAA-compatible)",
            "institution": "ECMWF",
            "source": "ECMWF IFS Operational Forecast",
            "history": f"Converted on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "conventions": "CF-1.7",
            "converted_for": "loczcit_iqr library compatibility",
        }
        
        # ================================================================
        # 6. VALIDAÇÕES FINAIS (IDÊNTICO ao ERA5DataLoader)
        # ================================================================
        expected_coords = {"time", "lat", "lon"}
        actual_coords = set(ds_out.coords)
        
        if actual_coords != expected_coords:
            extra = actual_coords - expected_coords
            missing = expected_coords - actual_coords
            raise RuntimeError(
                f"❌ Estrutura incompatível com NOAA!\n"
                f"  Extras: {extra}\n"
                f"  Faltando: {missing}"
            )
        
        # Validar range
        olr_mean = float(ds_out["olr"].mean())
        if not (self.OLR_VALID_RANGE[0] < olr_mean < self.OLR_VALID_RANGE[1]):
            logger.warning(
                f"OLR médio ({olr_mean:.2f} W/m²) fora do range típico "
                f"({self.OLR_VALID_RANGE[0]}-{self.OLR_VALID_RANGE[1]})"
            )
        
        # Testar compatibilidade com processor.py
        try:
            test_item = ds_out.time.max().values.item()
            if hasattr(test_item, "year"):
                logger.debug(f"✓ Compatível com processor.py")
            else:
                test_ts = pd.Timestamp(ds_out.time.max().values)
                logger.debug(f"✓ Compatível via pd.Timestamp (year={test_ts.year})")
        except Exception as e:
            logger.warning(f"Possível incompatibilidade: {e}")
        
        return ds_out
    
    def list_cached_files(self) -> List[dict]:
        """Lista arquivos em cache."""
        files = []
        for f in self.cache_dir.glob("ecmwf_ifs_*.grib2"):
            files.append({
                "filename": f.name,
                "path": str(f),
                "size_mb": f.stat().st_size / (1024 * 1024),
                "modified": datetime.fromtimestamp(f.stat().st_mtime),
            })
        return sorted(files, key=lambda x: x["modified"], reverse=True)
    
    def clear_cache(self, older_than_days: int | None = None, confirm: bool = False) -> int:
        """Limpa cache de arquivos GRIB."""
        if not confirm and older_than_days is None:
            logger.warning("Use confirm=True ou older_than_days para limpar cache")
            return 0
        
        count = 0
        cutoff = None
        
        if older_than_days is not None:
            cutoff = datetime.now() - timedelta(days=older_than_days)
        
        for f in self.cache_dir.glob("ecmwf_ifs_*.grib2"):
            should_remove = cutoff is None or (
                datetime.fromtimestamp(f.stat().st_mtime) < cutoff
            )
            
            if should_remove:
                try:
                    f.unlink()
                    count += 1
                except Exception as e:
                    logger.warning(f"Erro ao remover {f.name}: {e}")
        
        logger.info(f"Cache limpo: {count} arquivos")
        return count
    
    def __repr__(self) -> str:
        """Representação string."""
        n_cached = len(list(self.cache_dir.glob("ecmwf_ifs_*.grib2")))
        return (
            f"ECMWFForecastLoader(\n"
            f"  source={self.source},\n"
            f"  cache_dir={self.cache_dir},\n"
            f"  cached_files={n_cached}\n"
            f")"
        )


# =============================================================================
# FUNÇÕES DE CONVENIÊNCIA
# =============================================================================

def load_zcit_forecast(
    forecast_days: int = 5,
    area: Tuple[float, float, float, float] | None = None,
    cache_dir: str = "./ecmwf_forecast_cache",
) -> xr.Dataset:
    """
    Função rápida para carregar previsão de OLR para análise ZCIT.
    
    Parameters
    ----------
    forecast_days : int
        Dias de previsão (1-15)
    area : tuple, optional
        Área de estudo [lat_N, lon_W, lat_S, lon_E]
    cache_dir : str
        Diretório de cache
    
    Returns
    -------
    xr.Dataset
        Dados de OLR previsto no formato NOAA
    
    Examples
    --------
    >>> # Carregar previsão de 5 dias para ZCIT
    >>> forecast = load_zcit_forecast(5)
    >>> 
    >>> # Usar com LOCZCIT-IQR
    >>> from loczcit_iqr.core.processor import DataProcessor
    >>> processor = DataProcessor()
    >>> min_coords = processor.find_minimum_coordinates(forecast.olr)
    """
    loader = ECMWFForecastLoader(cache_dir=cache_dir)
    return loader.load_forecast(forecast_days=forecast_days, area=area)


# =============================================================================
# EXEMPLO DE USO
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    print("=" * 70)
    print("LOCZCIT-IQR: Previsão de ZCIT com ECMWF IFS")
    print("=" * 70)
    
    # Verificar dependências
    print("\n[1] Verificando dependências...")
    
    if not HAS_ECMWF_OPENDATA:
        print("❌ Faltando: pip install ecmwf-opendata")
        sys.exit(1)
    if not HAS_CFGRIB:
        print("❌ Faltando: pip install cfgrib eccodes")
        sys.exit(1)
    
    print("✅ Dependências OK!")
    
    # Criar loader
    print("\n[2] Inicializando...")
    loader = ECMWFForecastLoader(source="aws")
    print(loader)
    
    # Última rodada
    print("\n[3] Última previsão disponível...")
    run_time, run_hour = loader.get_latest_forecast_time()
    print(f"   Rodada: {run_time} ({run_hour:02d}z)")
    
    # Carregar previsão
    print("\n[4] Baixando previsão de OLR (5 dias)...")
    
    try:
        forecast = loader.load_forecast(forecast_days=5)
        
        print("\n✅ Previsão carregada!")
        print(f"   Dimensões: {dict(forecast.dims)}")
        print(f"   Coordenadas: {list(forecast.coords)}")
        print(f"   OLR médio: {forecast.olr.mean().values:.2f} W/m²")
        print(f"   OLR mín: {forecast.olr.min().values:.2f} W/m²")
        print(f"   OLR máx: {forecast.olr.max().values:.2f} W/m²")
        
        # Verificar compatibilidade
        print("\n[5] Verificando compatibilidade com LOCZCIT-IQR...")
        
        expected = {"lat", "lon"}
        actual = set(forecast.coords)
        
        if expected.issubset(actual):
            print("   ✅ Estrutura compatível!")
        
        print(f"   ✅ Unidade: {forecast.olr.attrs.get('units', 'N/A')}")
        
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("FIM")
    print("=" * 70)
