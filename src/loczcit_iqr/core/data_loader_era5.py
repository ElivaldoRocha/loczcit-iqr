"""
loczcit_iqr/core/data_loader_era5.py
=====================================

Módulo para download e carregamento de dados OLR do ERA5 (Copernicus).

Este módulo fornece uma alternativa ao NOAADataLoader quando os servidores
da NOAA estão indisponíveis (ex: paralisações do governo dos EUA).

Author: LOCZCIT-IQR Development Team
License: MIT
"""

from __future__ import annotations

import logging
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# Importações condicionais
try:
    import cdsapi

    HAS_CDSAPI = True
except ImportError:
    HAS_CDSAPI = False
    cdsapi = None
    warnings.warn(
        "cdsapi não instalado. Instale com: pip install cdsapi", ImportWarning
    )

# Logger
logger = logging.getLogger(__name__)


class ERA5DataLoader:
    """
    Loader para dados OLR do ERA5 (Copernicus Climate Data Store).

    Esta classe fornece uma alternativa ao NOAADataLoader quando os servidores
    da NOAA estão indisponíveis. Os dados são automaticamente convertidos para
    o formato NOAA OLR CDR para compatibilidade com loczcit_iqr.

    Attributes
    ----------
    cache_dir : Path
        Diretório para cache local dos arquivos
    cds_client : cdsapi.Client or None
        Cliente CDS para download de dados
    default_study_area : tuple
        Área padrão da ZCIT: [lat_max, lon_min, lat_min, lon_max]

    Examples
    --------
    >>> # Configurar credenciais (primeira vez)
    >>> loader = ERA5DataLoader()
    >>> loader.setup_credentials(key="uid:api-key")

    >>> # Carregar dados
    >>> data = loader.load_data(
    ...     start_date="2025-01-01",
    ...     end_date="2025-01-31"
    ... )

    >>> # Dados já vêm no formato NOAA (compatível com loczcit_iqr)
    >>> print(data.olr)  # Variável 'olr' em W m⁻²

    Notes
    -----
    Requer credenciais do Copernicus Climate Data Store (CDS).
    Registre-se gratuitamente em: https://cds.climate.copernicus.eu
    """

    # Constantes
    CDS_API_URL = "https://cds.climate.copernicus.eu/api"
    DATASET_NAME = "derived-era5-single-levels-daily-statistics"

    # Área padrão para ZCIT no Atlântico Tropical
    # Formato: [lat_norte, lon_oeste, lat_sul, lon_leste]
    DEFAULT_STUDY_AREA = (17, -80, -12, 4)

    # Limites válidos de OLR
    OLR_VALID_RANGE = (50.0, 450.0)

    def __init__(
        self,
        cache_dir: str | Path = "./era5_cache",
        cds_url: str | None = None,
        cds_key: str | None = None,
        timeout: int = 300,
        max_retries: int = 3,
        log_level: int | str = logging.INFO,
    ):
        """
        Inicializa o loader ERA5.

        Parameters
        ----------
        cache_dir : str or Path, optional
            Diretório para cache (default: "./era5_cache")
        cds_url : str, optional
            URL da API CDS (default: usa constante)
        cds_key : str, optional
            API key completa do CDS no formato "uid:key"
            (ex: "132638:05b92536-020d-4817-8709-7eeb367e268e")
            Se None, tenta ler de ~/.cdsapirc
        timeout : int, optional
            Timeout para requests em segundos (default: 300)
        max_retries : int, optional
            Número máximo de tentativas de download (default: 3)
        log_level : int or str, optional
            Nível de logging (default: logging.INFO)
        """
        # Configurar logging
        self._setup_logging(log_level)

        # Verificar dependências
        if not HAS_CDSAPI:
            raise ImportError(
                "cdsapi não instalado. Instale com:\n  pip install cdsapi"
            )

        # Configurar diretórios
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.timeout = timeout
        self.max_retries = max_retries

        # Cliente CDS
        self.cds_url = cds_url or self.CDS_API_URL
        self.cds_key = cds_key
        self.cds_client: cdsapi.Client | None = None

        # Tentar inicializar cliente
        self._initialize_cds_client()

        logger.info(f"ERA5DataLoader inicializado (cache: {self.cache_dir})")

    def _setup_logging(self, level: int | str) -> None:
        """Configura o sistema de logging."""
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        logger.setLevel(level)

    def _initialize_cds_client(self) -> None:
        """Inicializa o cliente CDS com credenciais."""
        try:
            if self.cds_key:
                # Usar credenciais fornecidas
                self.cds_client = cdsapi.Client(url=self.cds_url, key=self.cds_key)
                logger.info("Cliente CDS inicializado com credenciais fornecidas")
            else:
                # Tentar usar ~/.cdsapirc
                self.cds_client = cdsapi.Client()
                logger.info("Cliente CDS inicializado com ~/.cdsapirc")
        except Exception as e:
            logger.warning(
                f"Não foi possível inicializar cliente CDS: {e}\n"
                f"Use setup_credentials() para configurar."
            )
            self.cds_client = None

    def setup_credentials(self, key: str, save_to_file: bool = True) -> None:
        """
        Configura credenciais do CDS.

        Parameters
        ----------
        key : str
            API key completa do CDS no formato "uid:key"
            Exemplo: "132638:05b92536-020d-4817-8709-7eeb367e268e"

            Onde encontrar:
            1. Acesse: https://cds.climate.copernicus.eu/user
            2. Role até "API key"
            3. Copie a string completa mostrada
        save_to_file : bool, optional
            Se True, salva em ~/.cdsapirc (default: True)

        Examples
        --------
        >>> loader = ERA5DataLoader()
        >>> loader.setup_credentials(
        ...     key="132638:05b92536-020d-4817-8709-7eeb367e268e"
        ... )
        """
        self.cds_key = key

        # Reinicializar cliente
        self.cds_client = cdsapi.Client(url=self.cds_url, key=self.cds_key)

        logger.info("Credenciais CDS configuradas com sucesso")

        # Salvar em arquivo se solicitado
        if save_to_file:
            self._save_credentials_to_file(key)

    def _save_credentials_to_file(self, key: str) -> None:
        """Salva credenciais em ~/.cdsapirc."""
        cdsapirc_path = Path.home() / ".cdsapirc"

        try:
            with open(cdsapirc_path, "w") as f:
                f.write(f"url: {self.cds_url}\n")
                f.write(f"key: {key}\n")

            # Definir permissões (somente leitura/escrita para owner)
            cdsapirc_path.chmod(0o600)

            logger.info(f"Credenciais salvas em {cdsapirc_path}")
        except Exception as e:
            logger.warning(f"Não foi possível salvar credenciais: {e}")

    def load_data(
        self,
        start_date: str | datetime,
        end_date: str | datetime | None = None,
        area: tuple[float, float, float, float] | None = None,
        auto_download: bool = True,
        convert_to_noaa_format: bool = True,
        remove_cache: bool = False,
    ) -> xr.Dataset:
        """
        Carrega dados OLR do ERA5 para o período especificado.

        Parameters
        ----------
        start_date : str or datetime
            Data inicial (formato: 'YYYY-MM-DD')
        end_date : str or datetime, optional
            Data final (se None, usa fim do mês de start_date)
        area : tuple, optional
            Área [lat_norte, lon_oeste, lat_sul, lon_leste]
            Se None, usa área padrão da ZCIT
        auto_download : bool, optional
            Se True, baixa automaticamente se não em cache (default: True)
        convert_to_noaa_format : bool, optional
            Se True, converte para formato NOAA (default: True)
        remove_cache : bool, optional
            Se True, remove arquivo de cache após carregar (default: False)

        Returns
        -------
        xarray.Dataset
            Dados de OLR carregados (em formato NOAA se convert=True)

        Raises
        ------
        ValueError
            Se datas inválidas ou credenciais não configuradas
        RuntimeError
            Se download/conversão falhar

        Examples
        --------
        >>> loader = ERA5DataLoader()
        >>>
        >>> # Carregar um mês
        >>> data = loader.load_data("2025-01-01", "2025-01-31")
        >>>
        >>> # Carregar com área customizada
        >>> data = loader.load_data(
        ...     "2025-01-01", "2025-01-31",
        ...     area=[20, -100, -20, 20]
        ... )
        """
        # Validar credenciais
        if self.cds_client is None:
            raise ValueError(
                "Credenciais CDS não configuradas. Use:\n"
                "  loader.setup_credentials(key='...')"
            )

        # Processar datas
        start_dt, end_dt = self._process_dates(start_date, end_date)

        # Área de estudo
        study_area = area or self.DEFAULT_STUDY_AREA

        logger.info(f"Carregando dados ERA5: {start_dt.date()} a {end_dt.date()}")

        # Verificar cache
        cache_file = self._get_cache_filename(start_dt, end_dt, study_area)

        if cache_file.exists() and not remove_cache:
            logger.info(f"Usando arquivo do cache: {cache_file}")
            try:
                ds = xr.open_dataset(cache_file)
                logger.info("Dados carregados do cache com sucesso")
                return ds
            except Exception as e:
                logger.warning(f"Erro ao ler cache: {e}. Baixando novamente...")

        # Download se necessário
        if auto_download:
            downloaded_file = self._download_data(start_dt, end_dt, study_area)
        else:
            raise FileNotFoundError(
                "Arquivo não encontrado em cache e auto_download=False"
            )

        # Carregar dados
        logger.info("Carregando dados baixados...")
        ds_original = xr.open_dataset(downloaded_file)

        # Converter para formato NOAA se solicitado
        if convert_to_noaa_format:
            logger.info("Convertendo para formato NOAA...")
            ds = self._convert_to_noaa_format(ds_original)
        else:
            ds = ds_original

        # Salvar no cache (formato convertido)
        if convert_to_noaa_format:
            logger.info(f"Salvando no cache: {cache_file}")
            ds.to_netcdf(cache_file)

        # Remover arquivo original baixado se solicitado
        if remove_cache and downloaded_file.exists():
            downloaded_file.unlink()
            logger.debug(f"Arquivo temporário removido: {downloaded_file}")

        logger.info("Dados ERA5 carregados com sucesso!")
        return ds

    def _process_dates(
        self, start_date: str | datetime, end_date: str | datetime | None
    ) -> tuple[datetime, datetime]:
        """Processa e valida datas."""
        # Converter start_date
        if isinstance(start_date, str):
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start_dt = start_date

        # Converter end_date
        if end_date is None:
            # Fim do mês de start_date
            if start_dt.month == 12:
                end_dt = datetime(start_dt.year + 1, 1, 1) - timedelta(days=1)
            else:
                end_dt = datetime(start_dt.year, start_dt.month + 1, 1) - timedelta(
                    days=1
                )
        elif isinstance(end_date, str):
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_dt = end_date

        # Validar
        if end_dt < start_dt:
            raise ValueError("Data final deve ser posterior à inicial")

        if start_dt.year < 1940:
            raise ValueError("ERA5 disponível apenas a partir de 1940")

        current_date = datetime.now()
        if start_dt > current_date:
            raise ValueError("Data inicial não pode ser no futuro")

        return start_dt, end_dt

    def _get_cache_filename(
        self,
        start_dt: datetime,
        end_dt: datetime,
        area: tuple[float, float, float, float],
    ) -> Path:
        """Gera nome único para arquivo de cache."""
        # Hash da área para identificação
        area_str = f"{area[0]:.2f}_{area[1]:.2f}_{area[2]:.2f}_{area[3]:.2f}"

        filename = (
            f"era5_olr_noaa_format_"
            f"{start_dt.strftime('%Y%m%d')}_"
            f"{end_dt.strftime('%Y%m%d')}_"
            f"area_{area_str}.nc"
        )

        return self.cache_dir / filename

    def _download_data(
        self,
        start_dt: datetime,
        end_dt: datetime,
        area: tuple[float, float, float, float],
    ) -> Path:
        """
        Baixa dados do CDS.

        Returns
        -------
        Path
            Caminho do arquivo baixado
        """
        logger.info("Iniciando download do CDS...")

        # Gerar lista de anos e meses
        date_range = pd.date_range(start_dt, end_dt, freq="D")
        years = sorted(date_range.year.unique())

        # Download por ano/mês (otimização)
        downloaded_files = []

        for year in years:
            year_dates = date_range[date_range.year == year]
            months = sorted(year_dates.month.unique())

            for month in months:
                month_dates = year_dates[year_dates.month == month]
                days = [d.strftime("%d") for d in month_dates]

                temp_file = self._download_month(
                    year=str(year), month=f"{month:02d}", days=days, area=area
                )

                downloaded_files.append(temp_file)

        # Se múltiplos arquivos, concatenar
        if len(downloaded_files) == 1:
            return downloaded_files[0]
        logger.info("Concatenando múltiplos arquivos...")
        return self._concatenate_files(downloaded_files, start_dt, end_dt)

    def _download_month(
        self, year: str, month: str, days: list, area: tuple[float, float, float, float]
    ) -> Path:
        """Baixa dados de um mês específico."""
        logger.info(f"Baixando {year}-{month}...")

        request = {
            "product_type": "reanalysis",
            "variable": "top_net_thermal_radiation",
            "year": year,
            "month": month,
            "day": days,
            "daily_statistic": "daily_mean",
            "time_zone": "utc+00:00",
            "frequency": "1_hourly",
            "area": list(area),  # [lat_norte, lon_oeste, lat_sul, lon_leste]
        }

        # Nome do arquivo temporário
        temp_file = self.cache_dir / f"era5_temp_{year}_{month}.nc"

        # Download com retry
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Tentativa {attempt + 1}/{self.max_retries}...")

                self.cds_client.retrieve(self.DATASET_NAME, request).download(
                    str(temp_file)
                )

                logger.info(f"Download concluído: {temp_file}")
                return temp_file

            except Exception as e:
                logger.error(f"Erro no download: {e}")

                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"Download falhou após {self.max_retries} tentativas: {e}"
                    )

                # Backoff exponencial
                wait_time = 2**attempt
                logger.info(f"Aguardando {wait_time}s antes de tentar novamente...")
                time.sleep(wait_time)

    def _concatenate_files(
        self, files: list[Path], start_dt: datetime, end_dt: datetime
    ) -> Path:
        """
        Concatena múltiplos arquivos NetCDF mensais.

        CORREÇÃO: Fecha explicitamente datasets antes de deletar arquivos.
        """
        logger.info(f"Concatenando {len(files)} arquivo(s) mensal(is)...")

        datasets = []

        # ================================================================
        # ETAPA 1: CARREGAR DATASETS (COM AUTO-CLOSE)
        # ================================================================
        for file in files:
            try:
                # ✅ CORREÇÃO: Usar context manager + load()
                with xr.open_dataset(file, decode_times=True) as ds:
                    # Carregar na memória antes de fechar
                    ds_loaded = ds.load()
                    datasets.append(ds_loaded)

                logger.debug(f"Carregado: {file.name}")

            except Exception as e:
                logger.error(f"Erro ao carregar {file}: {e}")
                # Fechar datasets já abertos
                for ds in datasets:
                    try:
                        ds.close()
                    except:
                        pass
                raise

        # ================================================================
        # ETAPA 2: CONCATENAR
        # ================================================================
        try:
            # Concatenar ao longo da dimensão temporal
            combined = xr.concat(
                datasets, dim="valid_time", combine_attrs="drop_conflicts"
            )

            # Filtrar período exato
            combined = combined.sel(
                valid_time=slice(
                    start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
                )
            )

            logger.info(f"Concatenação concluída: {len(combined.valid_time)} dias")

        except Exception as e:
            logger.error(f"Erro na concatenação: {e}")
            # Fechar datasets
            for ds in datasets:
                try:
                    ds.close()
                except:
                    pass
            raise

        # ================================================================
        # ETAPA 3: SALVAR ARQUIVO COMBINADO
        # ================================================================
        output_file = (
            self.cache_dir
            / f"era5_combined_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}.nc"
        )

        try:
            logger.info(f"Salvando: {output_file.name}")

            # Salvar com compressão
            encoding = {
                var: {"zlib": True, "complevel": 4} for var in combined.data_vars
            }

            combined.to_netcdf(output_file, encoding=encoding)

        except Exception as e:
            logger.error(f"Erro ao salvar: {e}")
            raise
        finally:
            # ✅ CRÍTICO: Fechar dataset combinado
            try:
                combined.close()
            except:
                pass

        # ================================================================
        # ETAPA 4: LIMPAR ARQUIVOS TEMPORÁRIOS
        # ================================================================
        logger.info("Limpando arquivos temporários...")

        # Fechar todos os datasets explicitamente
        for ds in datasets:
            try:
                ds.close()
            except:
                pass

        # Aguardar Windows liberar arquivos
        import time

        time.sleep(0.5)

        # Deletar arquivos temporários
        for file in files:
            try:
                if file.exists():
                    file.unlink()
                    logger.debug(f"Removido: {file.name}")
            except PermissionError:
                # Se ainda bloqueado, apenas avisar (não falhar)
                logger.warning(
                    f"Não foi possível remover {file.name}. Arquivo pode estar em uso."
                )
            except Exception as e:
                logger.warning(f"Erro ao remover {file.name}: {e}")

        logger.info(f"✅ Arquivo concatenado criado: {output_file.name}")
        return output_file

    def _convert_to_noaa_format(self, ds_era5: xr.Dataset) -> xr.Dataset:
        """
        Converte dados ERA5 para formato NOAA OLR CDR.

        Conversões aplicadas:
        0. REMOVER coordenada 'number' (compatibilidade NOAA)
        1. Unidade: J m⁻² → W m⁻² (÷ 3600)
        2. Sinal: Convenção ECMWF → OLR (× -1)
        3. Dimensões: valid_time→time, latitude→lat, longitude→lon
        4. Variável: ttr → olr
        5. Metadados: Compatíveis com NOAA

        Notes
        -----
        Fórmula validada: olr = (ttr / 3600) * (-1)
        - Divide por 3600: converte J/m²/hora para W/m²
        - Multiplica por -1: inverte convenção ECMWF para OLR
        """
        logger.debug("Iniciando conversão para formato NOAA...")

        ds = ds_era5.copy()

        # ================================================================
        # 0. REMOVER COORDENADAS EXTRAS (COMPATIBILIDADE NOAA) ⚠️ CRÍTICO!
        # ================================================================
        logger.debug("🔧 Verificando coordenada 'number'...")

        # Método 1: Se 'number' é uma dimensão, fazer squeeze
        if "number" in ds.dims:
            logger.debug("  └─ Removendo 'number' como dimensão via squeeze")
            ds = ds.squeeze("number", drop=True)

        # Método 2: Se 'number' é coordenada, remover
        if "number" in ds.coords:
            logger.debug("  └─ Removendo 'number' como coordenada via drop_vars")
            try:
                ds = ds.drop_vars("number")
            except:
                pass

        # Método 3: Forçar remoção via reset_coords
        if "number" in ds.coords or "number" in ds.dims:
            logger.debug("  └─ Forçando remoção via reset_coords")
            try:
                ds = ds.reset_coords("number", drop=True)
            except:
                pass

        # Validação final CRÍTICA
        if "number" in ds.coords or "number" in ds.dims:
            raise RuntimeError(
                "❌ ERRO CRÍTICO: Não foi possível remover coordenada 'number'! "
                "Isso causará incompatibilidade com processor.py"
            )
        logger.debug("  ✓ Coordenada 'number' removida com sucesso")

        # ================================================================
        # 1. CONVERSÃO DE VALORES
        # ================================================================
        if "ttr" not in ds.data_vars:
            raise ValueError("Dataset não contém variável 'ttr'")

        # Conversão validada: (ttr / 3600) * (-1)
        ds["ttr"] = (ds["ttr"] / 3600.0) * -1.0

        # ================================================================
        # 2. RENOMEAR VARIÁVEL
        # ================================================================
        ds = ds.rename({"ttr": "olr"})

        # ================================================================
        # 3. RENOMEAR DIMENSÕES
        # ================================================================
        rename_dims = {}
        if "valid_time" in ds.dims:
            rename_dims["valid_time"] = "time"
        if "latitude" in ds.dims:
            rename_dims["latitude"] = "lat"
        if "longitude" in ds.dims:
            rename_dims["longitude"] = "lon"

        if rename_dims:
            ds = ds.rename(rename_dims)

        # ================================================================
        # 4. AJUSTAR COORDENADAS - CORREÇÃO DEFINITIVA
        # ================================================================
        # Coordenada temporal - GARANTIR COMPATIBILIDADE COM PROCESSOR
        if "time" in ds.coords:
            logger.debug("🔧 Convertendo coordenada temporal para datetime64[ns]...")

            # Obter valores atuais
            time_values = ds["time"].values

            # Converter para datetime64[ns] via pandas e extrair valores
            # CRÍTICO: usar .values para extrair array numpy do DatetimeIndex
            time_ns = pd.DatetimeIndex(time_values).values

            # Atribuir os valores convertidos de volta
            ds = ds.assign_coords(time=time_ns)

            # Atualizar atributos
            ds["time"].attrs.update(
                {"long_name": "time", "standard_name": "time", "axis": "T"}
            )

            logger.debug(f"   ✓ Time dtype: {ds.time.dtype}")
            logger.debug(f"   ✓ Time sample: {ds.time.values[0]}")

        # Coordenada de latitude
        if "lat" in ds.coords:
            # Garantir ordem Norte→Sul
            if ds["lat"].values[0] < ds["lat"].values[-1]:
                ds = ds.reindex(lat=ds["lat"][::-1])

            ds["lat"].attrs.update(
                {
                    "long_name": "latitude",
                    "standard_name": "latitude",
                    "units": "degrees_north",
                    "axis": "Y",
                }
            )

        # Coordenada de longitude
        if "lon" in ds.coords:
            lon_vals = ds["lon"].values

            # Converter para [-180, 180] se necessário
            if lon_vals.max() > 180:
                lon_vals = np.where(lon_vals > 180, lon_vals - 360, lon_vals)
                ds = ds.assign_coords(lon=lon_vals)
                ds = ds.sortby("lon")

            ds["lon"].attrs.update(
                {
                    "long_name": "longitude",
                    "standard_name": "longitude",
                    "units": "degrees_east",
                    "axis": "X",
                }
            )

        # ================================================================
        # 5. METADADOS
        # ================================================================
        ds["olr"].attrs = {
            "long_name": "Daily Mean Outgoing Longwave Radiation",
            "standard_name": "toa_outgoing_longwave_flux",
            "units": "W m**-2",
            "cell_methods": "time: mean",
            "valid_min": self.OLR_VALID_RANGE[0],
            "valid_max": self.OLR_VALID_RANGE[1],
            "source": "ERA5 Reanalysis (ECMWF)",
            "original_variable": "top_net_thermal_radiation",
            "conversion_formula": "(ttr / 3600) * (-1)",
            "conversion_note": (
                "Converted from J m⁻²/hour to W m⁻² by dividing by 3600 seconds. "
                "Sign inverted to match OLR convention (positive = outgoing)."
            ),
            "comment": "Converted from ERA5 format to NOAA OLR CDR format for compatibility with loczcit_iqr",
        }

        ds.attrs = {
            "title": "ERA5 Reanalysis - Outgoing Longwave Radiation (NOAA-compatible)",
            "institution": "European Centre for Medium-Range Weather Forecasts (ECMWF)",
            "source": "ERA5 Reanalysis",
            "history": f"Converted to NOAA format on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "conventions": "CF-1.7",
            "spatial_resolution": "0.25 degrees",
            "temporal_resolution": "daily",
            "conversion_method": "divide_by_3600_and_invert_sign",
            "converted_for": "loczcit_iqr library compatibility",
        }

        # Validar resultado
        olr_mean = float(ds["olr"].mean())
        if not (150 < olr_mean < 350):
            logger.warning(
                f"Média OLR ({olr_mean:.2f}) fora do range típico (150-350 W m⁻²)"
            )

        # ================================================================
        # 6. VALIDAÇÃO FINAL ESTRITA
        # ================================================================
        expected_coords = {"time", "lat", "lon"}
        actual_coords = set(ds.coords)

        if actual_coords != expected_coords:
            extra = actual_coords - expected_coords
            missing = expected_coords - actual_coords
            error_msg = "❌ Estrutura final incompatível com NOAA!\n"
            if extra:
                error_msg += f"  • Coordenadas extras: {extra}\n"
            if missing:
                error_msg += f"  • Coordenadas faltando: {missing}\n"
            raise RuntimeError(error_msg)

        # ================================================================
        # 7. TESTE DE COMPATIBILIDADE COM PROCESSOR (DEBUG)
        # ================================================================
        logger.debug("=== VALIDAÇÃO DE COMPATIBILIDADE ===")
        logger.debug(f"   Dimensões: {dict(ds.dims)}")
        logger.debug(f"   Coordenadas: {list(ds.coords)}")
        logger.debug(f"   Time dtype: {ds.time.dtype}")

        # Testar se .item() funciona corretamente
        try:
            test_item = ds.time.max().values.item()
            if hasattr(test_item, "year"):
                logger.debug(
                    f"   ✅ .item() retorna objeto datetime com .year: {test_item.year}"
                )
            else:
                logger.warning(
                    f"   ⚠️  .item() retorna {type(test_item)}, mas sem .year"
                )
                # Testar conversão alternativa
                test_ts = pd.Timestamp(ds.time.max().values)
                logger.debug(
                    f"   ✅ Conversão via pd.Timestamp funciona: {test_ts.year}"
                )
        except Exception as e:
            logger.error(f"   ❌ Erro ao testar .item(): {e}")

        logger.debug("✅ Conversão para formato NOAA concluída")

        return ds

    def clear_cache(
        self, confirm: bool = False, older_than_days: int | None = None
    ) -> int:
        """
        Limpa cache de arquivos ERA5.

        Parameters
        ----------
        confirm : bool, optional
            Se True, confirma a limpeza (default: False)
        older_than_days : int, optional
            Remove apenas arquivos mais antigos que N dias

        Returns
        -------
        int
            Número de arquivos removidos
        """
        if not confirm:
            logger.warning("Use confirm=True para confirmar limpeza do cache")
            return 0

        files_removed = 0
        cutoff_date = None

        if older_than_days:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)

        for file in self.cache_dir.glob("era5_*.nc"):
            should_remove = True

            if cutoff_date:
                file_mtime = datetime.fromtimestamp(file.stat().st_mtime)
                should_remove = file_mtime < cutoff_date

            if should_remove:
                try:
                    file.unlink()
                    files_removed += 1
                    logger.info(f"Removido: {file.name}")
                except Exception as e:
                    logger.error(f"Erro ao remover {file}: {e}")

        logger.info(f"Total removido: {files_removed} arquivo(s)")
        return files_removed

    def list_cached_files(self) -> list[dict]:
        """
        Lista arquivos em cache.

        Returns
        -------
        list of dict
            Lista com informações dos arquivos em cache
        """
        cached_files = []

        for file in self.cache_dir.glob("era5_*.nc"):
            cached_files.append(
                {
                    "filename": file.name,
                    "path": str(file),
                    "size_mb": file.stat().st_size / (1024 * 1024),
                    "modified": datetime.fromtimestamp(file.stat().st_mtime),
                }
            )

        return sorted(cached_files, key=lambda x: x["modified"], reverse=True)

    def get_info(self, filepath: str | Path) -> dict:
        """
        Obtém informações de um arquivo NetCDF.

        Parameters
        ----------
        filepath : str or Path
            Caminho do arquivo

        Returns
        -------
        dict
            Dicionário com informações do dataset
        """
        ds = xr.open_dataset(filepath)

        info = {
            "dimensions": dict(ds.dims),
            "variables": list(ds.data_vars),
            "coordinates": list(ds.coords),
            "time_range": None,
            "spatial_extent": None,
            "attributes": dict(ds.attrs),
        }

        # Range temporal
        if "time" in ds.coords:
            info["time_range"] = {
                "start": str(ds.time.min().values),
                "end": str(ds.time.max().values),
                "n_timesteps": len(ds.time),
            }

        # Extensão espacial
        if "lat" in ds.coords and "lon" in ds.coords:
            info["spatial_extent"] = {
                "lat_min": float(ds.lat.min()),
                "lat_max": float(ds.lat.max()),
                "lon_min": float(ds.lon.min()),
                "lon_max": float(ds.lon.max()),
            }

        # Estatísticas de OLR
        if "olr" in ds.data_vars:
            info["olr_statistics"] = {
                "mean": float(ds.olr.mean()),
                "std": float(ds.olr.std()),
                "min": float(ds.olr.min()),
                "max": float(ds.olr.max()),
                "missing_values": int(ds.olr.isnull().sum()),
                "missing_percent": float((ds.olr.isnull().sum() / ds.olr.size) * 100),
            }

        ds.close()
        return info

    def __repr__(self) -> str:
        """Representação string do loader."""
        status = "✓ Configurado" if self.cds_client else "✗ Não configurado"
        return (
            f"ERA5DataLoader(\n"
            f"  cache_dir={self.cache_dir},\n"
            f"  status={status},\n"
            f"  cached_files={len(list(self.cache_dir.glob('era5_*.nc')))}\n"
            f")"
        )


# ============================================================================
# FUNÇÕES DE CONVENIÊNCIA
# ============================================================================


def load_era5_olr(
    start_date: str,
    end_date: str | None = None,
    area: tuple[float, float, float, float] | None = None,
    cache_dir: str = "./era5_cache",
    **kwargs,
) -> xr.Dataset:
    """
    Função de conveniência para carregar dados ERA5 rapidamente.

    Parameters
    ----------
    start_date : str
        Data inicial (formato: 'YYYY-MM-DD')
    end_date : str, optional
        Data final (se None, usa fim do mês)
    area : tuple, optional
        Área [lat_norte, lon_oeste, lat_sul, lon_leste]
    cache_dir : str, optional
        Diretório de cache (default: "./era5_cache")
    **kwargs
        Argumentos adicionais para ERA5DataLoader.load_data()

    Returns
    -------
    xarray.Dataset
        Dados OLR no formato NOAA

    Examples
    --------
    >>> # Carregar janeiro de 2025
    >>> data = load_era5_olr("2025-01-01", "2025-01-31")
    >>> print(data.olr.mean())
    """
    loader = ERA5DataLoader(cache_dir=cache_dir)
    return loader.load_data(
        start_date=start_date, end_date=end_date, area=area, **kwargs
    )


# ============================================================================
# EXEMPLO DE USO
# ============================================================================

if __name__ == "__main__":
    """
    Exemplo de uso do ERA5DataLoader.
    
    Para executar este exemplo:
    1. Instale o cdsapi: pip install cdsapi
    2. Registre-se em: https://cds.climate.copernicus.eu
    3. Configure suas credenciais (veja exemplo abaixo)
    4. Execute: python data_loader_era5.py
    """

    # Configurar logging para visualizar progresso
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("=" * 70)
    print("EXEMPLO DE USO: ERA5DataLoader")
    print("=" * 70)

    # ========================================================================
    # PASSO 1: Criar instância do loader
    # ========================================================================
    print("\n[1] Criando loader...")
    loader = ERA5DataLoader(cache_dir="./era5_cache")
    print(loader)

    # ========================================================================
    # PASSO 2: Configurar credenciais (apenas primeira vez)
    # ========================================================================
    print("\n[2] Configurando credenciais...")
    print("IMPORTANTE: Substitua pela sua API key do CDS!")
    print("Como obter:")
    print("  1. Acesse: https://cds.climate.copernicus.eu/user")
    print("  2. Role até 'API key'")
    print("  3. Copie a string completa no formato 'uid:key'")

    # DESCOMENTE E CONFIGURE SUA CREDENCIAL:
    # loader.setup_credentials(
    #     key="132638:05b92536-020d-4817-8709-7eeb367e268e"  # Formato: "uid:key"
    # )

    # Verificar se já tem credenciais configuradas
    if loader.cds_client is None:
        print("\n⚠️  CREDENCIAIS NÃO CONFIGURADAS!")
        print("Execute loader.setup_credentials() antes de baixar dados.")
        sys.exit(0)

    # ========================================================================
    # PASSO 3: Carregar dados
    # ========================================================================
    print("\n[3] Carregando dados ERA5...")

    try:
        # Carregar janeiro de 2025
        data = loader.load_data(
            start_date="2025-01-01",
            end_date="2025-01-31",
            area=None,  # Usa área padrão da ZCIT
            auto_download=True,
            convert_to_noaa_format=True,
        )

        print("\n✅ Dados carregados com sucesso!")
        print(f"Dimensões: {data.dims}")
        print(f"Variáveis: {list(data.data_vars)}")
        print(f"Coordenadas: {list(data.coords)}")

        # ====================================================================
        # PASSO 4: Verificar dados
        # ====================================================================
        print("\n[4] Estatísticas OLR:")
        print(f"  Média: {data.olr.mean().values:.2f} W/m²")
        print(f"  Desvio: {data.olr.std().values:.2f} W/m²")
        print(f"  Mín: {data.olr.min().values:.2f} W/m²")
        print(f"  Máx: {data.olr.max().values:.2f} W/m²")

        # ====================================================================
        # PASSO 5: Verificar conversão
        # ====================================================================
        print("\n[5] Verificando conversão ERA5 → NOAA:")
        print(f"  Unidade: {data.olr.attrs.get('units', 'N/A')}")
        print(f"  Fórmula: {data.olr.attrs.get('conversion_formula', 'N/A')}")

        # Validar range
        mean_olr = float(data.olr.mean())
        if 150 < mean_olr < 350:
            print(f"\n✅ Média OLR ({mean_olr:.2f} W/m²) está no range esperado!")
        else:
            print(f"\n⚠️  Média OLR ({mean_olr:.2f} W/m²) fora do range típico!")

        # ====================================================================
        # PASSO 6: Validar compatibilidade NOAA
        # ====================================================================
        print("\n[6] Validando compatibilidade NOAA:")
        expected_coords = {"time", "lat", "lon"}
        actual_coords = set(data.coords)

        if actual_coords == expected_coords:
            print("  ✅ Estrutura 100% compatível com NOAA!")
        else:
            print(
                f"  ❌ Incompatível! Esperado: {expected_coords}, Atual: {actual_coords}"
            )

        # ====================================================================
        # PASSO 7: Testar compatibilidade com processor.py
        # ====================================================================
        print("\n[7] Testando compatibilidade com processor.py:")
        try:
            # Testar método que falha no processor
            test_item = data.time.max().values.item()
            if hasattr(test_item, "year"):
                print(f"  ✅ Método .item() compatível! Ano: {test_item.year}")
                print("  ✅ Pode usar com process_latest_period()")
            else:
                print(f"  ⚠️  .item() retorna {type(test_item)} sem .year")
                print("  ℹ️  Mas pd.Timestamp funciona como alternativa")
        except Exception as e:
            print(f"  ❌ Erro ao testar: {e}")

    except ValueError as e:
        print(f"\n❌ Erro de configuração: {e}")
        print("Configure suas credenciais primeiro!")
    except Exception as e:
        print(f"\n❌ Erro ao carregar dados: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 70)
    print("FIM DO EXEMPLO")
    print("=" * 70)
