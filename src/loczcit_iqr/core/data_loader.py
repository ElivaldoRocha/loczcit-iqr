"""
loczcit_iqr/core/data_loader.py
Classe para download e carregamento de dados OLR da NOAA
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
import xarray as xr
from tqdm import tqdm

try:
    import cftime

    HAS_CFTIME = True
except ImportError:
    HAS_CFTIME = False
    cftime = None  # type: ignore

try:
    import pyarrow

    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False
    pyarrow = None  # type: ignore
    print("É necessário ter pyarrow instalado")

try:
    import geopandas as gpd

    HAS_GEOPANDAS = True
except ImportError:
    HAS_GEOPANDAS = False
    gpd = None  # type: ignore
    print("É necessário ter geopandas instalado")

try:
    import regionmask as rm

    HAS_REGIONMASK = True
except ImportError:
    HAS_REGIONMASK = False
    rm = None  # type: ignore
    print("É necessário ter regionmask instalado")

# Configurar logger
logger = logging.getLogger(__name__)


class NOAADataLoader:
    """
    Classe para download e carregamento de dados OLR da NOAA

    Esta classe gerencia o download automático de dados de Radiação de Onda Longa
    Emergente (OLR) do arquivo NOAA e o carregamento para análise.

    Parameters
    ----------
    base_url : str
        URL base para download dos dados NOAA
    cache_dir : str
        Diretório para armazenamento local dos dados
    timeout : int
        Timeout padrão para requisições HTTP (segundos)
    max_retries : int
        Número máximo de tentativas de download

    Attributes
    ----------
    cache_metadata : dict
        Metadados sobre arquivos em cache

    Examples
    --------
    >>> loader = NOAADataLoader()
    >>> data = loader.load_data('2023-01-01', '2023-12-31')
    >>> print(f"Dados carregados: {data.dims}")

    Notes
    -----
    Os dados OLR da NOAA são disponibilizados em formato NetCDF com
    resolução de 1° x 1° e frequência diária desde 1979.

    References
    ----------
    .. [1] Lee, H.T., 2014: Climate Algorithm Theoretical Basis Document (C-ATBD):
           Outgoing Longwave Radiation (OLR) - Daily. NOAA's CDR Program.
    """

    # URL validada da NOAA (constante de classe)
    NOAA_OLR_URL = (
        "https://www.ncei.noaa.gov/data/outgoing-longwave-radiation-daily/access/"
    )

    # Limites válidos para OLR (W/m²)
    OLR_VALID_RANGE = (50.0, 500.0)

    def __init__(
        self,
        base_url: str | None = None,
        cache_dir: str = "./data_cache",
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self.base_url = (base_url or self.NOAA_OLR_URL).rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries

        # Diretório para metadados do cache
        self.metadata_file = self.cache_dir / ".cache_metadata.json"
        self.cache_metadata = self._load_cache_metadata()

        # Padrões de nomes de arquivos
        self.filename_patterns = {
            "preliminary": "olr-daily_v01r02-preliminary_{start}_{end}.nc",
            "final": "olr-daily_v01r02_{start}_{end}.nc",
        }

        # Configurar logging
        self._setup_logging()

    def _setup_logging(self) -> None:
        """Configura logging para a classe, evitando duplicatas."""
        # Só configura se o logger ainda não tiver handlers
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

    def _load_cache_metadata(self) -> dict[str, dict]:
        """Carrega metadados do cache"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Erro ao carregar metadados do cache: {e}")
        return {}

    def _save_cache_metadata(self) -> None:
        """Salva metadados do cache"""
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(self.cache_metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar metadados do cache: {e}")

    def _check_connectivity(self, timeout: int | None = None) -> bool:
        """
        Verifica conectividade com servidor NOAA

        Parameters
        ----------
        timeout : int, optional
            Timeout em segundos

        Returns
        -------
        bool
            True se conectado, False caso contrário
        """
        timeout = timeout or self.timeout
        try:
            response = requests.head(self.base_url, timeout=timeout)
            return response.status_code < 400
        except requests.RequestException as e:
            logger.warning(f"Sem conectividade: {e}")
            return False

    def _handle_http_error(self, response: requests.Response) -> None:
        """
        Trata erros HTTP específicos

        Parameters
        ----------
        response : requests.Response
            Resposta HTTP

        Raises
        ------
        FileNotFoundError
            Se arquivo não existe (404)
        PermissionError
            Se acesso negado (403)
        RuntimeError
            Para outros erros HTTP
        """
        if response.status_code == 404:
            raise FileNotFoundError(
                f"Arquivo não encontrado no servidor NOAA: {response.url}"
            )
        if response.status_code == 403:
            raise PermissionError(f"Acesso negado ao servidor NOAA: {response.url}")
        if response.status_code >= 500:
            raise RuntimeError(
                f"Erro no servidor NOAA ({response.status_code}): {response.reason}"
            )
        response.raise_for_status()

    def _validate_cached_file(self, file_path: Path, max_age_days: int = 365) -> bool:
        """
        Valida arquivo em cache

        Parameters
        ----------
        file_path : Path
            Caminho do arquivo
        max_age_days : int
            Idade máxima em dias

        Returns
        -------
        bool
            True se arquivo é válido
        """
        if not file_path.exists():
            return False

        # Verifica tamanho mínimo (1MB)
        if file_path.stat().st_size < 1024 * 1024:
            logger.warning(f"Arquivo muito pequeno: {file_path}")
            return False

        # Verifica idade
        age_days = (
            datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
        ).days
        if age_days > max_age_days:
            logger.warning(f"Arquivo com {age_days} dias (máximo: {max_age_days})")
            return False

        # Verifica integridade se houver checksum
        file_key = str(file_path.name)
        if file_key in self.cache_metadata:
            expected_checksum = self.cache_metadata[file_key].get("checksum")
            if expected_checksum:
                actual_checksum = self._calculate_checksum(file_path)
                if actual_checksum != expected_checksum:
                    logger.error(f"Checksum inválido para {file_path}")
                    return False

        return True

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calcula checksum MD5 do arquivo"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _generate_filename(
        self,
        start_date: datetime,
        end_date: datetime,
        preliminary: bool = True,
    ) -> str:
        """
        Gera nome do arquivo baseado nas datas

        Parameters
        ----------
        start_date : datetime
            Data inicial
        end_date : datetime
            Data final
        preliminary : bool
            Se True, usa dados preliminares (mais recentes)

        Returns
        -------
        str
            Nome do arquivo
        """
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        pattern_key = "preliminary" if preliminary else "final"
        filename = self.filename_patterns[pattern_key].format(
            start=start_str, end=end_str
        )

        return filename

    def _get_available_files(self) -> list[str]:
        """
        Obtém lista de arquivos disponíveis no servidor NOAA

        Returns
        -------
        list
            Lista de arquivos disponíveis
        """
        try:
            response = requests.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()

            # Parse HTML simples para extrair links .nc
            import re

            nc_files = re.findall(r'href="(olr-daily_v01r02[^"]*\.nc)"', response.text)
            return sorted(set(nc_files))

        except Exception as e:
            logger.error(f"Erro ao obter lista de arquivos: {e}")
            return []

    def _find_best_file(self, start_date: datetime, end_date: datetime) -> str | None:
        """
        Encontra o melhor arquivo disponível, tratando o ano corrente como caso especial.
        """
        available_files = self._get_available_files()
        if not available_files:
            logger.error("Nenhum arquivo disponível no servidor")
            return None

        year = start_date.year
        current_year = datetime.now().year

        # =======================================================
        # NOVA LÓGICA INTELIGENTE PARA O ANO CORRENTE
        # =======================================================
        if year == current_year:
            logger.info(f"Buscando arquivo para o ano corrente ({year})...")
            # O padrão para o ano corrente é sempre preliminar e tem data final dinâmica
            pattern = f"olr-daily_v01r02-preliminary_{year}0101_"

            for f in available_files:
                if f.startswith(pattern):
                    logger.info(f"Arquivo do ano corrente encontrado: {f}")
                    return f

            logger.warning(
                f"Nenhum arquivo preliminar encontrado para o ano corrente {year}."
            )
            # Se não encontrar, continua para a lógica antiga como um fallback improvável.
        # =======================================================

        # Lógica antiga, agora usada principalmente para anos passados
        year_pattern = f"{year}0101_{year}1231"
        year_files = [f for f in available_files if year_pattern in f]

        if year_files:
            # Preferir dados preliminares se existirem (pode acontecer para o ano anterior recente)
            prelim_files = [f for f in year_files if "preliminary" in f]
            if prelim_files:
                logger.info(f"Usando arquivo anual preliminar: {prelim_files[0]}")
                return prelim_files[0]

            logger.info(f"Usando arquivo anual final: {year_files[0]}")
            return year_files[0]

        logger.warning(f"Nenhum arquivo adequado encontrado para {year}")
        return None

    def download_file(
        self,
        filename: str,
        force_download: bool = False,
        show_progress: bool = True,
        verify_ssl: bool = True,
    ) -> Path:
        """
        Download de um arquivo específico com retry e validações

        Parameters
        ----------
        filename : str
            Nome do arquivo para download
        force_download : bool
            Se True, força novo download mesmo se arquivo existir
        show_progress : bool
            Se True, mostra barra de progresso
        verify_ssl : bool
            Se True, verifica certificado SSL

        Returns
        -------
        Path
            Caminho do arquivo baixado

        Raises
        ------
        ConnectionError
            Se não houver conectividade
        RuntimeError
            Se download falhar após todas tentativas
        """
        file_path = self.cache_dir / filename

        # Verificar cache
        if not force_download and self._validate_cached_file(file_path):
            logger.info(f"Usando arquivo do cache: {file_path}")
            return file_path

        # Verificar conectividade
        if not self._check_connectivity():
            raise ConnectionError(
                "Sem conectividade com servidor NOAA. "
                "Verifique sua conexão com a internet."
            )

        url = f"{self.base_url}/{filename}"

        # Tentar download com retry
        for attempt in range(self.max_retries):
            try:
                logger.info(
                    f"Download tentativa {attempt + 1}/{self.max_retries}: {filename}"
                )

                # Headers para identificar cliente
                headers = {
                    "User-Agent": "LOCZCIT-IQR/1.0 (https://github.com/seu-usuario/loczcit)"
                }

                response = requests.get(
                    url,
                    timeout=self.timeout,
                    stream=True,
                    verify=verify_ssl,
                    headers=headers,
                )

                self._handle_http_error(response)

                # Obter tamanho do arquivo
                total_size = int(response.headers.get("content-length", 0))

                # Salvar em arquivo temporário
                temp_path = file_path.with_suffix(".tmp")

                with open(temp_path, "wb") as f:
                    if show_progress and total_size > 0:
                        with tqdm(
                            total=total_size,
                            unit="B",
                            unit_scale=True,
                            desc=filename,
                        ) as pbar:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    pbar.update(len(chunk))
                    else:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)

                # Validar arquivo baixado
                if not self._validate_netcdf(temp_path):
                    temp_path.unlink()
                    raise ValueError("Arquivo NetCDF inválido")

                # Calcular checksum
                checksum = self._calculate_checksum(temp_path)

                # Mover para destino final
                temp_path.replace(file_path)

                # Atualizar metadados
                self.cache_metadata[filename] = {
                    "checksum": checksum,
                    "download_date": datetime.now().isoformat(),
                    "size_bytes": file_path.stat().st_size,
                    "url": url,
                }
                self._save_cache_metadata()

                logger.info(f"Download concluído: {file_path}")
                return file_path

            except Exception as e:
                logger.error(f"Erro na tentativa {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise RuntimeError(
                        f"Download falhou após {self.max_retries} tentativas: {e}"
                    )
                # Backoff exponencial
                wait_time = 2**attempt
                logger.info(f"Aguardando {wait_time}s antes de tentar novamente...")
                time.sleep(wait_time)

    def _validate_netcdf(self, file_path: Path) -> bool:
        """
        Valida arquivo NetCDF

        Parameters
        ----------
        file_path : Path
            Caminho do arquivo

        Returns
        -------
        bool
            True se arquivo é válido
        """
        try:
            with xr.open_dataset(file_path) as ds:
                # Verificar variáveis essenciais
                required_vars = ["olr"]
                for var in required_vars:
                    if var not in ds.data_vars:
                        logger.error(f"Variável '{var}' não encontrada em {file_path}")
                        return False

                # Verificar dimensões
                required_dims = ["time", "lat", "lon"]
                for dim in required_dims:
                    if dim not in ds.dims:
                        logger.error(f"Dimensão '{dim}' não encontrada em {file_path}")
                        return False

                # Verificar coordenadas
                if len(ds.time) == 0:
                    logger.error("Dataset vazio (sem dados temporais)")
                    return False

                # Verificar intervalo de valores OLR
                olr_min = float(ds.olr.min())
                olr_max = float(ds.olr.max())

                if (
                    olr_min < self.OLR_VALID_RANGE[0]
                    or olr_max > self.OLR_VALID_RANGE[1]
                ):
                    logger.warning(
                        f"Valores OLR fora do intervalo esperado: "
                        f"[{olr_min:.1f}, {olr_max:.1f}] W/m²"
                    )

                return True

        except Exception as e:
            logger.error(f"Erro ao validar NetCDF: {e}")
            return False

    def load_data(
        self,
        start_date: str | datetime,
        end_date: str | datetime | None = None,
        study_area: tuple[float, float, float, float] | None = None,
        auto_download: bool = True,
        quality_control: bool = True,
        remove_leap_days: bool = True,
    ) -> xr.Dataset:
        """
        Carrega dados OLR para o período especificado

        Parameters
        ----------
        start_date : str or datetime
            Data inicial (formato: 'YYYY-MM-DD' ou datetime)
        end_date : str or datetime, optional
            Data final. Se None, usa 31/12 do ano inicial
        study_area : tuple, optional
            Área de estudo (lat_min, lat_max, lon_min, lon_max)
        auto_download : bool
            Se True, baixa automaticamente se arquivo não existir
        quality_control : bool
            Se True, aplica controle de qualidade aos dados
        remove_leap_days : bool
            Se True, remove dias 29 de fevereiro de anos bissextos

        Returns
        -------
        xarray.Dataset
            Dados de OLR carregados e processados

        Raises
        ------
        ValueError
            Se parâmetros forem inválidos
        FileNotFoundError
            Se arquivo não existir e auto_download=False
        RuntimeError
            Se houver erro no carregamento

        Examples
        --------
        >>> loader = NOAADataLoader()
        >>> # Carregar ano completo
        >>> data = loader.load_data('2023-01-01', '2023-12-31')
        >>> # Carregar com área específica
        >>> data = loader.load_data('2023-01-01', study_area=(-10, 10, -50, -30))
        """
        # Validar e converter datas
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date is None:
            end_date = datetime(start_date.year, 12, 31)
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        # Validar período
        if end_date < start_date:
            raise ValueError("Data final deve ser posterior à data inicial")

        if start_date.year < 1979:
            raise ValueError("Dados OLR disponíveis apenas a partir de 1979")

        # Encontrar arquivo apropriado
        filename = self._find_best_file(start_date, end_date)

        if filename is None:
            available = self._get_available_files()
            raise ValueError(
                f"Nenhum arquivo encontrado para o período {start_date.date()} - {end_date.date()}.\n"
                f"Arquivos disponíveis: {available[:5]}..."
                if available
                else "Nenhum arquivo disponível."
            )

        # Download se necessário
        file_path = self.cache_dir / filename

        if not file_path.exists() and auto_download:
            file_path = self.download_file(filename)
        elif not file_path.exists():
            raise FileNotFoundError(
                f"Arquivo {filename} não encontrado em {self.cache_dir}. "
                "Use auto_download=True para download automático."
            )

        # Carregar dados
        logger.info(f"Carregando dados de: {file_path}")
        try:
            time_coder = xr.coders.CFDatetimeCoder(use_cftime=True)
            ds = xr.open_dataset(file_path, decode_times=time_coder, decode_coords=True)

            logger.debug(f"N dias antes de slice: {len(ds.time)}")

            # Filtrar período solicitado
            ds = ds.sel(
                time=slice(
                    start_date.strftime("%Y-%m-%d"),
                    end_date.strftime("%Y-%m-%d"),
                )
            )

            logger.debug(f"N dias após slice: {len(ds.time)}")

            if len(ds.time) == 0:
                raise ValueError(
                    f"Nenhum dado encontrado para o período "
                    f"{start_date.date()} - {end_date.date()}"
                )

            # --- INÍCIO DA CORREÇÃO ---
            # 1. Corrigir longitudes (0-360 para -180-180) ANTES de filtrar a área
            if ds.lon.max() > 180:
                ds = self._fix_longitude(ds)

            # 2. Filtrar área de estudo DEPOIS da correção de longitude
            if study_area:
                lat_min, lat_max, lon_min, lon_max = study_area

                # Validar coordenadas
                if not (-90 <= lat_min < lat_max <= 90):
                    raise ValueError("Latitudes inválidas")
                if not (-180 <= lon_min < lon_max <= 180):
                    raise ValueError("Longitudes inválidas")

                ds = ds.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))
            # --- FIM DA CORREÇÃO ---

            # Remover dias bissextos se solicitado e necessário
            if remove_leap_days:
                ds = self._remove_leap_days(ds)

            # Aplicar controle de qualidade
            if quality_control:
                ds = self._apply_quality_control(ds)

            # Adicionar metadados
            ds.attrs.update(
                {
                    "source": "NOAA OLR Daily CDR",
                    "download_date": datetime.now().isoformat(),
                    "loczcit_version": "1.0.0",
                    "original_file": filename,
                    "leap_days_removed": remove_leap_days,
                }
            )

            logger.info(f"Dados carregados com sucesso: {ds.dims}")
            return ds

        except Exception as e:
            logger.error(f"Erro ao carregar {file_path}: {e}")
            raise RuntimeError(f"Erro ao carregar dados: {e}")

    def _fix_longitude(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Corrige longitudes de 0-360 para -180-180

        Parameters
        ----------
        ds : xarray.Dataset
            Dataset com longitudes 0-360

        Returns
        -------
        xarray.Dataset
            Dataset com longitudes -180-180
        """
        # Criar nova coordenada de longitude
        lon_attrs = ds.lon.attrs.copy()

        ds = ds.assign_coords(lon=(ds.lon + 180) % 360 - 180)

        # Reordenar para manter continuidade
        ds = ds.sortby("lon")

        # Restaurar atributos
        ds.lon.attrs = lon_attrs
        ds.lon.attrs["standard_name"] = "longitude"
        ds.lon.attrs["units"] = "degrees_east"

        return ds

    def _remove_leap_days(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Remove dias 29 de fevereiro de anos bissextos

        Parameters
        ----------
        ds : xarray.Dataset
            Dataset original

        Returns
        -------
        xarray.Dataset
            Dataset sem dias 29/02
        """
        try:
            # Obter valores de tempo
            time_values = ds.time.values

            # Detectar tipo de tempo e extrair mês/dia
            if len(time_values) > 0:
                # Verificar se é cftime
                first_time = time_values[0]

                if hasattr(first_time, "month") and hasattr(first_time, "day"):
                    # É um objeto cftime (DatetimeGregorian, DatetimeNoLeap, etc.)
                    # Criar máscara para excluir 29/02
                    mask = np.array(
                        [not (t.month == 2 and t.day == 29) for t in time_values]
                    )

                    # Contar quantos dias 29/02 foram encontrados
                    n_leap_days = (~mask).sum()
                    if n_leap_days > 0:
                        logger.info(f"Removendo {n_leap_days} dias 29/02")
                        ds = ds.sel(time=mask)
                    else:
                        logger.debug("Nenhum dia 29/02 encontrado")

                else:
                    # Tentar converter para pandas datetime
                    try:
                        time_index = pd.to_datetime(time_values)
                        mask = ~((time_index.month == 2) & (time_index.day == 29))

                        n_leap_days = (~mask).sum()
                        if n_leap_days > 0:
                            logger.info(f"Removendo {n_leap_days} dias 29/02")
                            ds = ds.sel(time=mask)
                        else:
                            logger.debug("Nenhum dia 29/02 encontrado")

                    except Exception as e:
                        logger.warning(
                            f"Não foi possível verificar dias bissextos. "
                            f"Tipo de tempo: {type(first_time)}. Erro: {e}"
                        )

            return ds

        except Exception as e:
            logger.error(f"Erro ao remover dias bissextos: {e}")
            # Em caso de erro, retornar dataset original
            return ds

    def _apply_quality_control(self, ds: xr.Dataset) -> xr.Dataset:
        """
        Aplica controle de qualidade aos dados

        Parameters
        ----------
        ds : xarray.Dataset
            Dataset original

        Returns
        -------
        xarray.Dataset
            Dataset com QC aplicado
        """
        # Verificar e corrigir valores fora do intervalo
        olr_min, olr_max = self.OLR_VALID_RANGE

        # Contar valores problemáticos
        n_below = (ds.olr < olr_min).sum().item()
        n_above = (ds.olr > olr_max).sum().item()
        n_nan = ds.olr.isnull().sum().item()

        if n_below > 0 or n_above > 0:
            logger.warning(
                f"Valores fora do intervalo [{olr_min}, {olr_max}] W/m²: "
                f"{n_below} abaixo, {n_above} acima"
            )

            # Mascarar valores inválidos
            ds["olr"] = ds.olr.where((ds.olr >= olr_min) & (ds.olr <= olr_max))

        if n_nan > 0:
            total_points = ds.olr.size
            nan_percent = (n_nan / total_points) * 100
            logger.warning(f"Dados faltantes: {n_nan} ({nan_percent:.1f}%)")

        # Adicionar flag de qualidade
        ds["qc_flag"] = xr.where(
            ds.olr.isnull(),
            2,  # 2 = dado faltante
            xr.where(
                (ds.olr < olr_min) | (ds.olr > olr_max),
                1,  # 1 = fora do intervalo
                0,  # 0 = bom
            ),
        )

        ds.qc_flag.attrs = {
            "long_name": "quality_control_flag",
            "flag_values": [0, 1, 2],
            "flag_meanings": "good out_of_range missing",
        }

        return ds

    def list_cached_files(self) -> list[dict[str, Any]]:
        """
        Lista arquivos em cache com informações

        Returns
        -------
        list
            Lista de dicionários com informações dos arquivos
        """
        cached_files = []

        for file_path in self.cache_dir.glob("*.nc"):
            file_info = {
                "filename": file_path.name,
                "path": str(file_path),
                "size_mb": file_path.stat().st_size / (1024 * 1024),
                "modified": datetime.fromtimestamp(file_path.stat().st_mtime),
                "valid": self._validate_cached_file(file_path),
            }

            # Adicionar metadados se disponíveis
            if file_path.name in self.cache_metadata:
                file_info.update(self.cache_metadata[file_path.name])

            cached_files.append(file_info)

        return sorted(cached_files, key=lambda x: x["modified"], reverse=True)

    def clear_cache(
        self, confirm: bool = False, older_than_days: int | None = None
    ) -> int:
        """
        Limpa cache de arquivos

        Parameters
        ----------
        confirm : bool
            Se True, confirma a limpeza
        older_than_days : int, optional
            Remove apenas arquivos mais antigos que N dias

        Returns
        -------
        int
            Número de arquivos removidos
        """
        if not confirm:
            logger.warning("Use confirm=True para confirmar a limpeza do cache")
            return 0

        files_removed = 0
        cutoff_date = None

        if older_than_days:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)

        for file_path in self.cache_dir.glob("*.nc"):
            should_remove = True

            if cutoff_date:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                should_remove = file_mtime < cutoff_date

            if should_remove:
                try:
                    file_path.unlink()
                    files_removed += 1
                    logger.info(f"Removido: {file_path.name}")

                    # Remover dos metadados
                    if file_path.name in self.cache_metadata:
                        del self.cache_metadata[file_path.name]

                except Exception as e:
                    logger.error(f"Erro ao remover {file_path}: {e}")

        # Salvar metadados atualizados
        if files_removed > 0:
            self._save_cache_metadata()

        logger.info(f"Total de arquivos removidos: {files_removed}")
        return files_removed

    def get_data_info(self, filename: str) -> dict[str, Any]:
        """
        Obtém informações detalhadas sobre um dataset

        Parameters
        ----------
        filename : str
            Nome do arquivo

        Returns
        -------
        dict
            Informações do dataset

        Raises
        ------
        FileNotFoundError
            Se arquivo não existir
        """
        file_path = self.cache_dir / filename

        if not file_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

        with xr.open_dataset(file_path) as ds:
            # Informações básicas
            info = {
                "filename": filename,
                "file_path": str(file_path),
                "file_size_mb": file_path.stat().st_size / (1024 * 1024),
                "dimensions": dict(ds.dims),
                "variables": list(ds.data_vars.keys()),
                "coordinates": list(ds.coords.keys()),
                "time_range": (
                    str(ds.time.min().values)[:10],
                    str(ds.time.max().values)[:10],
                ),
                "spatial_extent": {
                    "lat_min": float(ds.lat.min()),
                    "lat_max": float(ds.lat.max()),
                    "lon_min": float(ds.lon.min()),
                    "lon_max": float(ds.lon.max()),
                },
                "attributes": dict(ds.attrs),
            }

            # Estatísticas de OLR
            if "olr" in ds.data_vars:
                olr_stats = {
                    "mean": float(ds.olr.mean()),
                    "std": float(ds.olr.std()),
                    "min": float(ds.olr.min()),
                    "max": float(ds.olr.max()),
                    "missing_values": int(ds.olr.isnull().sum()),
                    "missing_percent": float(
                        (ds.olr.isnull().sum() / ds.olr.size) * 100
                    ),
                }
                info["olr_statistics"] = olr_stats

            # Informações de qualidade se disponível
            if "qc_flag" in ds.data_vars:
                qc_values, qc_counts = np.unique(
                    ds.qc_flag.values[~np.isnan(ds.qc_flag.values)],
                    return_counts=True,
                )
                info["quality_control"] = {
                    int(val): int(count)
                    for val, count in zip(qc_values, qc_counts, strict=False)
                }

        return info

    def download_year_data(self, year: int, show_progress: bool = True) -> Path:
        """
        Método de conveniência para baixar dados de um ano completo

        Parameters
        ----------
        year : int
            Ano para download
        show_progress : bool
            Mostrar progresso

        Returns
        -------
        Path
            Caminho do arquivo baixado

        Examples
        --------
        >>> loader = NOAADataLoader()
        >>> file_path = loader.download_year_data(2023)
        >>> data = xr.open_dataset(file_path)
        """
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)

        filename = self._find_best_file(start_date, end_date)
        if filename:
            return self.download_file(filename, show_progress=show_progress)
        raise ValueError(f"Nenhum arquivo disponível para o ano {year}")

    def get_server_status(self) -> dict[str, Any]:
        """
        Verifica status do servidor NOAA

        Returns
        -------
        dict
            Status do servidor e estatísticas
        """
        status = {
            "server_url": self.base_url,
            "connectivity": False,
            "response_time_ms": None,
            "available_files": 0,
            "last_check": datetime.now().isoformat(),
        }

        # Testar conectividade
        start_time = time.time()
        status["connectivity"] = self._check_connectivity()
        status["response_time_ms"] = int((time.time() - start_time) * 1000)

        # Contar arquivos disponíveis
        if status["connectivity"]:
            try:
                files = self._get_available_files()
                status["available_files"] = len(files)

                # Anos disponíveis
                years = set()
                for f in files:
                    # Extrair ano do nome do arquivo
                    import re

                    year_match = re.search(r"(\d{4})0101", f)
                    if year_match:
                        years.add(int(year_match.group(1)))

                status["available_years"] = sorted(years)

            except Exception as e:
                logger.error(f"Erro ao verificar arquivos: {e}")

        return status

    def download_current_year_data(self, show_progress: bool = True) -> Path:
        """
        Método de conveniência para baixar dados do ano corrente, que ainda está em andamento.

        Este método busca pelo arquivo preliminar do ano atual, cujo nome de
        arquivo tem uma data final dinâmica.

        Parameters
        ----------
        show_progress : bool
            Se True, mostra a barra de progresso do download.

        Returns
        -------
        Path
            Caminho do arquivo baixado.

        Raises
        ------
        FileNotFoundError
            Se nenhum arquivo para o ano corrente for encontrado no servidor.
        """
        logger.info("Procurando arquivo de dados para o ano corrente...")

        # Obter o ano atual
        current_year = datetime.now().year

        # Obter a lista de todos os arquivos disponíveis no servidor
        available_files = self._get_available_files()
        if not available_files:
            raise FileNotFoundError(
                "Não foi possível obter a lista de arquivos do servidor NOAA."
            )

        # Padrão de busca para o arquivo preliminar do ano corrente
        # Ex: 'olr-daily_v01r02-preliminary_20250101_'
        file_pattern = f"olr-daily_v01r02-preliminary_{current_year}0101_"

        target_file = None
        # Procura na lista de arquivos um que comece com o padrão definido
        for filename in available_files:
            if filename.startswith(file_pattern):
                target_file = filename
                logger.info(f"Arquivo do ano corrente encontrado: {target_file}")
                break

        # Se um arquivo foi encontrado, inicia o download
        if target_file:
            return self.download_file(target_file, show_progress=show_progress)
        raise FileNotFoundError(
            f"Nenhum arquivo de dados preliminares encontrado para o ano de {current_year}."
        )

    def estimate_download_size(
        self,
        start_date: str | datetime,
        end_date: str | datetime | None = None,
    ) -> dict[str, Any]:
        """
        Estima tamanho do download para um período

        Parameters
        ----------
        start_date : str or datetime
            Data inicial
        end_date : str or datetime, optional
            Data final

        Returns
        -------
        dict
            Estimativa de tamanho e tempo
        """
        # Converter datas
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date is None:
            end_date = datetime(start_date.year, 12, 31)
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        # Estimar baseado em médias conhecidas
        days = (end_date - start_date).days + 1

        # Tamanho médio por dia de dados OLR (~0.5 MB/dia para global 1°x1°)
        estimated_mb = days * 0.5

        # Estimar tempo de download (assumindo 1 MB/s)
        estimated_seconds = estimated_mb

        return {
            "period_days": days,
            "estimated_size_mb": round(estimated_mb, 1),
            "estimated_download_time_seconds": round(estimated_seconds, 1),
            "estimated_download_time_readable": self._format_time(estimated_seconds),
        }

    def _format_time(self, seconds: float) -> str:
        """Formata tempo em formato legível"""
        if seconds < 60:
            return f"{int(seconds)} segundos"
        if seconds < 3600:
            return f"{int(seconds / 60)} minutos"
        return f"{seconds / 3600:.1f} horas"

    def load_data_dual_scale(
        self,
        start_date: str | datetime,
        end_date: str | datetime | None = None,
        study_area: tuple[float, float, float, float]
        | str
        | Any
        | None = None,  # Any para gpd.GeoDataFrame
        auto_download: bool = True,
        quality_control: bool = True,
        remove_leap_days: bool = True,
        return_study_area_subset: bool = True,
        mask_to_shape: bool = False,
    ) -> xr.Dataset | tuple[xr.Dataset | None, xr.Dataset | None]:
        """
        Carrega dados com estratégia dupla escala: globais + study area.

        ANALOGIA DO FOTÓGRAFO PROFISSIONAL 📸
        É como tirar duas fotos do mesmo evento:
        1. Foto panorâmica (dados globais) - para contexto completo
        2. Foto focada (study area) - para análise detalhada

        Parameters
        ----------
        start_date : str or datetime
            Data inicial
        end_date : str or datetime, optional
            Data final
        study_area : tuple, str or geopandas.GeoDataFrame, optional
            Área de estudo. Pode ser:
            - tuple: (lat_min, lat_max, lon_min, lon_max) para bounding box.
            - str: Caminho para arquivo de geometria (ex: .shp, .geojson, .parquet).
            - geopandas.GeoDataFrame: Objeto GeoDataFrame já carregado.
            Se None, tenta usar a geometria padrão da biblioteca.
        auto_download : bool
            Se True, baixa automaticamente se necessário
        quality_control : bool
            Se True, aplica controle de qualidade
        remove_leap_days : bool
            Se True, remove dias bissextos
        return_study_area_subset : bool
            Se True, retorna (dados_globais, dados_study_area)
            Se False, retorna apenas dados_globais
        mask_to_shape : bool, optional
            Se True e uma geometria de área de estudo é fornecida/carregada,
            mascara os dados do subset para a forma exata da geometria.
            Requer geopandas e regionmask. Se False, usa recorte por bounding box.
            (Padrão: False)

        Returns
        -------
        xr.Dataset or Tuple[Optional[xr.Dataset], Optional[xr.Dataset]]
            Dados globais ou (dados_globais, dados_study_area)

        Examples
        --------
        >>> loader = NOAADataLoader()
        >>> # Retornar ambos, com recorte por BBOX da geometria padrão
        >>> dados_globais, dados_study = loader.load_data_dual_scale(
        ...     '2024-03-01', '2024-03-31',
        ...     return_study_area_subset=True
        ... )
        >>> # Retornar ambos, com mascaramento pela forma da geometria padrão
        >>> dados_globais, dados_study_masked = loader.load_data_dual_scale(
        ...     '2024-03-01', '2024-03-31',
        ...     return_study_area_subset=True,
        ...     mask_to_shape=True
        ... )
        """

        logger.info("🌍 Carregando dados com estratégia dupla escala...")

        # ====================================================================
        # NOVA LÓGICA: VERIFICAR CACHE PRIMEIRO, SERVIDOR DEPOIS
        # ====================================================================

        # Converter datas para datetime se necessário
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date is None:
            end_date = datetime(start_date.year, 12, 31)
        elif isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        logger.info("🏪 ETAPA 0: Verificando cache local primeiro...")

        # 1. PRIMEIRO: Verificar quais arquivos estão no cache
        cached_files = list(self.cache_dir.glob("*.nc"))
        logger.info(f"📋 Encontrados {len(cached_files)} arquivos em cache")

        # 2. Tentar determinar o nome do arquivo baseado no ano
        year = start_date.year
        target_filename = None

        # 2.1. Primeiro tentar padrões conhecidos sem acessar servidor
        possible_patterns = [
            # Para anos anteriores (dados finais)
            f"olr-daily_v01r02_{year}0101_{year}1231.nc",
            # Para ano corrente (dados preliminares) - precisamos encontrar no cache
            # pois o nome tem data final dinâmica
        ]

        # 2.2. Verificar se algum dos padrões conhecidos está no cache
        for pattern in possible_patterns:
            candidate_path = self.cache_dir / pattern
            if candidate_path.exists() and self._validate_cached_file(candidate_path):
                target_filename = pattern
                logger.info(f"✅ Arquivo encontrado no cache: {target_filename}")
                break

        # 2.3. Se não encontrou pelos padrões, procurar por ano no cache
        if not target_filename:
            logger.info("🔍 Procurando arquivos do ano no cache...")
            year_pattern = f"{year}0101"
            for cached_file in cached_files:
                if year_pattern in cached_file.name and self._validate_cached_file(
                    cached_file
                ):
                    target_filename = cached_file.name
                    logger.info(
                        f"✅ Arquivo do ano encontrado no cache: {target_filename}"
                    )
                    break

        # ====================================================================
        # SE NÃO ENCONTROU NO CACHE, ENTÃO TENTAR SERVIDOR (APENAS SE auto_download=True)
        # ====================================================================

        if not target_filename:
            if not auto_download:
                logger.error(
                    f"❌ Nenhum arquivo para {year} encontrado no cache e auto_download=False"
                )
                return (None, None) if return_study_area_subset else None

            logger.info("📞 Não encontrado no cache. Consultando servidor NOAA...")

            # Só agora tentar acessar servidor
            try:
                target_filename = self._find_best_file(start_date, end_date)
                if not target_filename:
                    logger.error(
                        f"❌ Nenhum arquivo disponível para {year} no servidor"
                    )
                    return (None, None) if return_study_area_subset else None
            except Exception as e:
                logger.error(f"❌ Erro ao consultar servidor: {e}")
                if "503" in str(e) or "Service Unavailable" in str(e):
                    logger.info(
                        "🔄 Servidor temporariamente indisponível. Tentando usar cache..."
                    )
                    # Última tentativa: usar qualquer arquivo do cache que contenha dados do ano
                    for cached_file in cached_files:
                        if str(year) in cached_file.name:
                            target_filename = cached_file.name
                            logger.warning(
                                f"⚠️ Usando arquivo do cache (não validado): {target_filename}"
                            )
                            break

                    if not target_filename:
                        logger.error(
                            "❌ Nenhuma opção disponível (sem servidor e sem cache)"
                        )
                        return (None, None) if return_study_area_subset else None
                else:
                    return (None, None) if return_study_area_subset else None

        # ====================================================================
        # ETAPA 1: CARREGAR DADOS GLOBAIS USANDO O ARQUIVO DETERMINADO
        # ====================================================================

        file_path = self.cache_dir / target_filename

        # Download se necessário
        if not file_path.exists() and auto_download:
            try:
                logger.info(f"⬇️ Baixando arquivo: {target_filename}")
                file_path = self.download_file(target_filename)
            except Exception as e:
                logger.error(f"❌ Erro no download: {e}")
                return (None, None) if return_study_area_subset else None
        elif not file_path.exists():
            logger.error(
                f"❌ Arquivo {target_filename} não encontrado e auto_download=False"
            )
            return (None, None) if return_study_area_subset else None

        # Carregar dados usando o método load_data, mas passando o arquivo específico
        logger.info("📡 Carregando dados globais (contexto completo)...")
        try:
            # Usar diretamente o método de carregamento robusto
            dados_globais = carregar_olr_robusto(
                caminho_arquivo=file_path,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                study_area=None,  # Sempre None para dados globais
                debug=False,
            )

            if dados_globais is None:
                logger.error("❌ Falha ao carregar dados globais")
                return (None, None) if return_study_area_subset else None

            # Aplicar processamentos adicionais
            if remove_leap_days:
                dados_globais = self._remove_leap_days(dados_globais)

            if quality_control:
                dados_globais = self._apply_quality_control(dados_globais)

            logger.info(f"✅ Dados globais carregados: {dados_globais.sizes}")

        except Exception as e:
            logger.error(f"❌ Erro ao carregar dados globais: {e}")
            return (None, None) if return_study_area_subset else None

        if not return_study_area_subset:
            logger.info(
                "📊 Subset da área de estudo não solicitado. Retornando apenas dados globais."
            )
            return dados_globais

        # ====================================================================
        # ETAPA 2: PROCESSAR SUBSET DA ÁREA DE ESTUDO
        # ====================================================================

        logger.info("🎯 Processando subset da área de estudo...")
        dados_study_area = None
        gdf_study_area = None

        # 2.1. Determinar/Carregar a geometria (gdf_study_area)
        if study_area is None:
            default_shapefile_path = (
                Path(__file__).resolve().parent.parent.parent  # ✅ Sobe 3 níveis
                / "data"
                / "shapefiles"
                / "Area_LOCZCIT.parquet"
            )
            if default_shapefile_path.exists() and HAS_GEOPANDAS and HAS_PYARROW:
                try:
                    logger.info(
                        f"📍 Carregando geometria padrão de: {default_shapefile_path}"
                    )
                    gdf_study_area = gpd.read_parquet(default_shapefile_path)
                except Exception as e_shape:
                    logger.warning(
                        f"⚠️ Não foi possível carregar a geometria padrão: {e_shape}"
                    )
            else:
                logger.warning(
                    "⚠️ Geometria padrão não encontrada ou dependências (geopandas/pyarrow) faltando."
                )
        elif isinstance(study_area, str) and HAS_GEOPANDAS:
            try:
                logger.info(f"📍 Carregando geometria do arquivo: {study_area}")
                gdf_study_area = gpd.read_file(study_area)
            except Exception as e_shape:
                logger.warning(
                    f"⚠️ Não foi possível carregar a geometria do arquivo '{study_area}': {e_shape}"
                )
        elif HAS_GEOPANDAS and isinstance(study_area, gpd.GeoDataFrame):
            logger.info("📍 Usando GeoDataFrame fornecido como área de estudo.")
            gdf_study_area = study_area

        # 2.2. Processar o subset (mascarar ou recortar)
        if gdf_study_area is not None:
            if mask_to_shape and HAS_REGIONMASK:
                logger.info("🎭 Mascarando dados para a forma da geometria...")
                try:
                    if gdf_study_area.crs and gdf_study_area.crs.to_epsg() != 4326:
                        gdf_study_area = gdf_study_area.to_crs(epsg=4326)

                    if "number" not in gdf_study_area.columns:
                        gdf_study_area = (
                            gdf_study_area.reset_index(drop=True)
                            .reset_index()
                            .rename(columns={"index": "number"})
                        )

                    mask = rm.mask_geopandas(
                        gdf_study_area, dados_globais.lon, dados_globais.lat
                    )
                    dados_study_area = dados_globais.where(mask.notnull())

                    # Recortar para o bounding box para otimizar
                    (
                        min_lon,
                        min_lat,
                        max_lon,
                        max_lat,
                    ) = gdf_study_area.total_bounds
                    dados_study_area = dados_study_area.sel(
                        lon=slice(min_lon, max_lon),
                        lat=slice(min_lat, max_lat),
                    )
                    logger.info(
                        f"✅ Dados mascarados para a geometria: {dados_study_area.sizes}"
                    )

                except Exception as e_mask:
                    logger.error(
                        f"❌ Erro ao aplicar máscara com regionmask: {e_mask}. Recorrendo ao recorte por BBOX."
                    )
                    (
                        min_lon,
                        min_lat,
                        max_lon,
                        max_lat,
                    ) = gdf_study_area.total_bounds
                    dados_study_area = dados_globais.sel(
                        lat=slice(min_lat, max_lat),
                        lon=slice(min_lon, max_lon),
                    )
            else:
                if not HAS_REGIONMASK and mask_to_shape:
                    logger.warning(
                        "⚠️ Regionmask não instalado. Recorrendo ao recorte por BBOX da geometria."
                    )
                logger.info("✂️ Recortando dados pelo BBOX da geometria...")
                (
                    min_lon,
                    min_lat,
                    max_lon,
                    max_lat,
                ) = gdf_study_area.total_bounds
                dados_study_area = dados_globais.sel(
                    lat=slice(min_lat, max_lat), lon=slice(min_lon, max_lon)
                )
                logger.info(
                    f"✅ Dados recortados por BBOX da geometria: {dados_study_area.sizes}"
                )

        elif isinstance(study_area, tuple) and len(study_area) == 4:
            lat_s, lat_n, lon_w, lon_e = study_area
            logger.info(
                f"✂️ Recortando dados pelo BBOX fornecido: LAT({lat_s:.2f}:{lat_n:.2f}), LON({lon_w:.2f}:{lon_e:.2f})"
            )
            dados_study_area = dados_globais.sel(
                lat=slice(lat_s, lat_n), lon=slice(lon_w, lon_e)
            )

        # 2.3. Retornar os resultados
        if dados_study_area is not None and dados_study_area.olr.notnull().any():
            logger.info("✅ Retornando (dados_globais, dados_study_area).")
            # Checar se os dados foram carregados corretamente
            print(f"✅ Dados globais: {dados_globais.sizes}")
            print(f"✅ Study area: {dados_study_area.sizes}")
            return dados_globais, dados_study_area
        logger.warning(
            "⚠️ Não foi possível criar o subset da área de estudo ou o subset está vazio. Retornando (dados_globais, None)."
        )
        return dados_globais, None

    def __repr__(self) -> str:
        """Representação string da classe"""
        n_cached = len(list(self.cache_dir.glob("*.nc")))
        cache_size_mb = sum(f.stat().st_size for f in self.cache_dir.glob("*.nc")) / (
            1024 * 1024
        )

        return (
            f"NOAADataLoader(\n"
            f"  base_url='{self.base_url}',\n"
            f"  cache_dir='{self.cache_dir}',\n"
            f"  cached_files={n_cached},\n"
            f"  cache_size_mb={cache_size_mb:.1f}\n"
            f")"
        )

    def __str__(self) -> str:
        """String amigável da classe"""
        return f"NOAA OLR Data Loader (cache: {self.cache_dir})"


def diagnosticar_arquivo_netcdf(caminho_arquivo):
    """
    Função para diagnosticar problemas em arquivos NetCDF.

    Como um "médico" que examina o arquivo para encontrar o problema.
    """
    print(f"\n🏥 DIAGNÓSTICO: {Path(caminho_arquivo).name}")
    print("-" * 40)

    try:
        # Tentar abrir sem decodificar tempo para ver os dados brutos
        print("🔍 Abrindo arquivo sem decodificação de tempo...")
        ds_raw = xr.open_dataset(caminho_arquivo, decode_times=False)

        print("✅ Arquivo aberto com sucesso!")
        print(f"   Dimensões: {dict(ds_raw.dims)}")
        print(f"   Variáveis: {list(ds_raw.data_vars)}")
        print(f"   Coordenadas: {list(ds_raw.coords)}")

        # Verificar coordenada de tempo
        if "time" in ds_raw.coords:
            time_values = ds_raw.time.values
            print("\n📅 Coordenada 'time':")
            print(f"   Primeiros valores: {time_values[:5]}")
            print(f"   Atributos: {ds_raw.time.attrs}")

        # ================================================
        # BLOCO NOVO PARA VERIFICAR LONGITUDE
        # ================================================
        if "lon" in ds_raw.coords:
            lon_values = ds_raw.lon.values
            print("\n🌍 Coordenada 'lon':")
            print(f"   Shape: {lon_values.shape}")
            # Imprime os 5 primeiros e 5 últimos valores para ver o intervalo
            print(f"   Primeiros valores: {lon_values[:5]}")
            print(f"   Últimos valores: {lon_values[-5:]}")
            print(f"   Atributos: {ds_raw.lon.attrs}")
        # ================================================

        # ================================================
        # BLOCO NOVO PARA VERIFICAR LATITUDE
        # ================================================
        if "lat" in ds_raw.coords:
            lat_values = ds_raw.lat.values
            print("\n🌍 Coordenada 'lat':")
            print(f"   Shape: {lat_values.shape}")
            print(f"   Primeiros valores: {lat_values[:5]}")
            print(f"   Últimos valores: {lat_values[-5:]}")
            print(f"   Atributos: {ds_raw.lat.attrs}")
        # ================================================

        # Verificar variável OLR
        if "olr" in ds_raw.data_vars:
            olr_data = ds_raw.olr
            print("\n🌡️ Variável 'olr':")
            print(f"   Shape: {olr_data.shape}")
            if olr_data.size > 0:
                print(f"   Min: {np.nanmin(olr_data.values):.1f}")
                print(f"   Max: {np.nanmax(olr_data.values):.1f}")
            else:
                print("   ❌ Array vazio!")

        ds_raw.close()
        return True

    except Exception as e:
        print(f"❌ Erro ao diagnosticar: {e}")
        return False


def carregar_olr_robusto(
    caminho_arquivo,
    start_date=None,
    end_date=None,
    study_area=None,
    debug=True,
):
    """
    Função robusta para carregar dados OLR com tratamento de erros.

    Como um "técnico especializado" que sabe lidar com arquivos problemáticos.
    """
    if debug:
        print(f"\n🔧 CARREGAMENTO ROBUSTO: {Path(caminho_arquivo).name}")
        print("-" * 40)

    try:
        # Método 1: Tentar carregamento padrão
        if debug:
            print("🎯 Tentativa 1: Carregamento padrão...")

        # Usamos cftime para compatibilidade com os dados da NOAA
        ds = xr.open_dataset(caminho_arquivo, use_cftime=True)

        if debug:
            print("✅ Carregamento padrão bem-sucedido!")

    except Exception as e1:
        if debug:
            print(f"❌ Falha no método padrão: {e1}")
            print("🎯 Tentativa 2: Sem decodificação automática de tempo...")

        try:
            # Método 2: Sem decodificação automática
            ds = xr.open_dataset(caminho_arquivo, decode_times=False)

            # Converter tempo manualmente
            if "time" in ds.coords:
                time_units = ds.time.attrs.get("units", "days since 1970-01-01")
                if debug:
                    print(f"   Unidades de tempo detectadas: {time_units}")

                # Usar a decodificação do xarray é mais seguro
                ds["time"] = xr.decode_cf(ds).time

                if debug:
                    print(f"✅ Tempo convertido manualmente: {ds.time.values[:3]}")

        except Exception as e2:
            if debug:
                print(f"❌ Falha no método 2: {e2}")
            raise RuntimeError("Não foi possível carregar o arquivo com nenhum método")

    # Aplicar filtros se fornecidos
    if debug:
        print("\n📊 Dataset carregado:")
        print(f"   Dimensões: {dict(ds.dims)}")
        if hasattr(ds, "time") and len(ds.time) > 0:
            print(
                f"   Período: {str(ds.time.values[0])[:19]} até {str(ds.time.values[-1])[:19]}"
            )

    # ==========================================================
    # BLOCO DE CORREÇÃO DE LONGITUDE ADICIONADO AQUI
    # Converte as longitudes ANTES de qualquer filtro espacial.
    # ==========================================================
    if "lon" in ds.coords and ds.lon.max() > 180:
        if debug:
            print("\n🔄 Convertendo longitudes de 0-360 para -180-180...")
        # Salva os atributos originais
        lon_attrs = ds.lon.attrs
        # Converte a coordenada
        ds = ds.assign_coords(lon=(((ds.lon + 180) % 360) - 180))
        # Reordena os dados pela nova coordenada
        ds = ds.sortby("lon")
        # Restaura os atributos
        ds.lon.attrs = lon_attrs
        if debug:
            print(
                f"✅ Longitudes convertidas. Novo intervalo: {ds.lon.min().item():.1f} a {ds.lon.max().item():.1f}"
            )

    # Filtrar período se especificado
    if start_date and end_date and "time" in ds.coords:
        try:
            if debug:
                print(f"\n🗓️ Filtrando período: {start_date} até {end_date}")

            ds_filtered = ds.sel(time=slice(start_date, end_date))

            if len(ds_filtered.time) == 0:
                print("⚠️ AVISO: Nenhum dado encontrado no período especificado!")
                return None

            ds = ds_filtered

            if debug:
                print(f"✅ Período filtrado: {len(ds.time)} dias")

        except Exception as e:
            if debug:
                print(f"❌ Erro ao filtrar período: {e}")
            return None

    # Filtrar área se especificada
    if study_area and "lat" in ds.coords and "lon" in ds.coords:
        try:
            lat_min, lat_max, lon_min, lon_max = study_area

            if debug:
                print(
                    f"\n🌍 Filtrando área: Lat({lat_min}, {lat_max}), Lon({lon_min}, {lon_max})"
                )

            ds = ds.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))

            if len(ds.lon) == 0 or len(ds.lat) == 0:
                if debug:
                    print("❌ ERRO: A seleção da área resultou em um dataset vazio!")
                return None

            if debug:
                print(f"✅ Área filtrada: {len(ds.lat)} lats x {len(ds.lon)} lons")

        except Exception as e:
            if debug:
                print(f"❌ Erro ao filtrar área: {e}")
            return None

    # Verificação final
    if "olr" in ds.data_vars:
        valid_data = np.isfinite(ds.olr.values).sum()
        if valid_data == 0:
            if debug:
                print("\n❌ ERRO FINAL: Nenhum dado OLR válido após todos os filtros!")
            return None

        if debug:
            print(f"\n✅ Dados OLR válidos encontrados: {valid_data:,}")

    return ds


_loader_instance = NOAADataLoader()


# Função auxiliar para uso rápido
def load_olr_data(start_date: str, end_date: str | None = None, **kwargs) -> xr.Dataset:
    """
    Função de conveniência para carregar dados OLR de forma rápida e segura.

    Esta função utiliza uma instância única do NOAADataLoader para encontrar,
    baixar (se necessário) e carregar os dados usando a lógica mais robusta
    disponível.

    Parameters
    ----------
    start_date : str
        Data inicial no formato 'YYYY-MM-DD'.
    end_date : str, optional
        Data final no formato 'YYYY-MM-DD'. Se None, usa o final do ano de start_date.
    **kwargs
        Argumentos adicionais como:
        - study_area: tuple(lat_min, lat_max, lon_min, lon_max)
        - auto_download: bool (padrão: True)
        - debug: bool (para a função de carregamento robusto)

    Returns
    -------
    xarray.Dataset or None
        Dados OLR carregados ou None se ocorrer um erro.
    """
    try:
        # Extrai argumentos dos kwargs com valores padrão
        auto_download = kwargs.get("auto_download", True)
        study_area = kwargs.get("study_area")
        debug = kwargs.get("debug", False)

        # Converte as datas de string para datetime
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end_dt = datetime(start_dt.year, 12, 31)

        # 1. Usa a instância única para encontrar o nome do arquivo correto
        filename = _loader_instance._find_best_file(start_dt, end_dt)
        if not filename:
            raise FileNotFoundError(
                f"Nenhum arquivo de dados encontrado para o período de {start_date} a {end_date}"
            )

        file_path = _loader_instance.cache_dir / filename

        # 2. Usa a instância para baixar o arquivo, se necessário
        if not file_path.exists() and auto_download:
            print(f"Arquivo '{filename}' não encontrado no cache. Baixando...")
            _loader_instance.download_file(filename)
        elif not file_path.exists():
            raise FileNotFoundError(
                f"Arquivo {filename} não está no cache e auto_download=False."
            )

        # 3. Chama a função de carregamento robusto com o caminho do arquivo
        dados = carregar_olr_robusto(
            caminho_arquivo=file_path,
            start_date=start_date,
            end_date=end_date,
            study_area=study_area,
            debug=debug,
        )

        return dados

    except Exception as e:
        print(f"❌ Erro na função de conveniência load_olr_data: {e}")
        return None
