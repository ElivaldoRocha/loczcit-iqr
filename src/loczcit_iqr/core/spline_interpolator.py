"""
loczcit_iqr/core/spline_interpolator.py

Módulo para interpolação de coordenadas da ZCIT usando B-spline e outros métodos.

Este módulo implementa diferentes técnicas de interpolação para criar linhas suaves
a partir de pontos discretos, especialmente útil para traçar a Zona de Convergência
Intertropical (ZCIT).
"""

import hashlib
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import interpolate, stats
from scipy.ndimage import gaussian_filter1d
from shapely.geometry import LineString

# Configuração do logger do módulo
logger = logging.getLogger(__name__)


class InterpolationMethod(Enum):
    """Métodos de interpolação disponíveis."""

    BSPLINE = 'bspline'
    CUBIC = 'cubic'
    AKIMA = 'akima'
    PCHIP = 'pchip'
    LINEAR = 'linear'


@dataclass
class SplineParameters:
    """
    Parâmetros para configuração da interpolação spline.

    Attributes
    ----------
    method : InterpolationMethod
        Método de interpolação a ser utilizado.
    smooth_factor : Union[str, float]
        Fator de suavização ('auto', 'low', 'medium', 'high' ou valor numérico).
    degree : int
        Grau do spline (aplicável principalmente para B-spline).
    num_points_output : int
        Número de pontos desejados na linha interpolada.
    max_curvature_threshold : Optional[float]
        Limiar máximo de curvatura aceitável.
    extrapolate_flag : bool
        Se permite extrapolação além dos limites dos dados.
    reference_latitude : Optional[float]
        Latitude de referência para cálculo de pesos.
    """

    method: InterpolationMethod = InterpolationMethod.BSPLINE
    smooth_factor: Union[str, float] = 'auto'
    degree: int = 3
    num_points_output: int = 100
    max_curvature_threshold: Optional[float] = None
    extrapolate_flag: bool = False
    reference_latitude: Optional[float] = None

    def to_cache_key(self) -> Tuple[str, ...]:
        """Converte parâmetros em tupla para uso como chave de cache."""
        return (
            self.method.value,
            str(self.smooth_factor),
            self.degree,
            self.num_points_output,
            self.max_curvature_threshold,
            self.extrapolate_flag,
            str(self.reference_latitude),
        )


class SplineInterpolator:
    """
    Interpolador para criação de linhas suaves a partir de coordenadas discretas.

    Esta classe implementa vários métodos de interpolação para criar representações
    contínuas da ZCIT a partir de pontos observados.

    Attributes
    ----------
    default_method : InterpolationMethod
        Método de interpolação padrão.
    default_smooth_factor : Union[str, float]
        Fator de suavização padrão.
    default_degree : int
        Grau padrão do spline.
    min_input_points : int
        Número mínimo de pontos necessários para interpolação.

    Examples
    --------
    >>> interpolator = SplineInterpolator()
    >>> coords = [(10.0, 5.0), (15.0, 4.5), (20.0, 5.2)]
    >>> line, stats = interpolator.interpolate(coords)
    """

    # Constantes de classe
    SMOOTH_PRESETS: Dict[str, float] = {
        'low': 0.1,
        'medium': 0.5,
        'high': 1.0,
        'very_high': 2.0,
    }

    DEFAULT_CACHE_SIZE: int = 10
    MIN_POINTS_FOR_SMOOTHING: int = 5
    LARGE_GAP_MULTIPLIER: float = 5.0
    MAX_OSCILLATION_RATIO: float = 0.3
    MAX_LATITUDE_JUMP: float = 10.0

    def __init__(
        self,
        default_method: str = 'bspline',
        default_smooth_factor: Union[str, float] = 'auto',
        default_degree: int = 3,
        min_input_points: int = 3,
        log_level: Union[int, str] = logging.INFO,
        default_reference_latitude: float = 0.0,
    ) -> None:
        """
        Inicializa o interpolador com parâmetros padrão.

        Parameters
        ----------
        default_method : str, optional
            Método de interpolação padrão (default: 'bspline').
        default_smooth_factor : Union[str, float], optional
            Fator de suavização padrão (default: 'auto').
        default_degree : int, optional
            Grau padrão do spline (default: 3).
        min_input_points : int, optional
            Número mínimo de pontos de entrada (default: 3).
        log_level : Union[int, str], optional
            Nível de logging (default: logging.INFO).
        default_reference_latitude : float, optional
            Latitude de referência padrão (default: 0.0).

        Raises
        ------
        ValueError
            Se o método padrão não for válido.
        """
        self._setup_logging(log_level)

        # Validação e configuração do método
        try:
            self.default_method = InterpolationMethod(default_method.lower())
        except ValueError:
            valid_methods = [m.value for m in InterpolationMethod]
            logger.error(
                f"Método '{default_method}' inválido. "
                f'Métodos válidos: {valid_methods}'
            )
            raise ValueError(f"Método '{default_method}' inválido")

        # Configuração dos parâmetros padrão
        self.default_smooth_factor = default_smooth_factor
        self.default_degree = default_degree
        self.default_reference_latitude = default_reference_latitude
        self.min_input_points = max(min_input_points, 2)

        # Cache para resultados de interpolação
        self._interpolation_cache: Dict[
            str, Tuple[LineString, Dict[str, Any]]
        ] = {}
        self._cache_size = self.DEFAULT_CACHE_SIZE

        # Mapeamento de métodos de interpolação
        self._interpolation_methods: Dict[InterpolationMethod, Callable] = {
            InterpolationMethod.BSPLINE: self._interpolate_bspline,
            InterpolationMethod.CUBIC: self._interpolate_cubic,
            InterpolationMethod.AKIMA: self._interpolate_akima,
            InterpolationMethod.PCHIP: self._interpolate_pchip,
            InterpolationMethod.LINEAR: self._interpolate_linear,
        }

        logger.info(
            f"SplineInterpolator inicializado: método='{self.default_method.value}', "
            f'lat_ref={self.default_reference_latitude:.2f}°'
        )

    def _setup_logging(self, level: Union[int, str]) -> None:
        """Configura o sistema de logging."""
        class_logger = logging.getLogger(__name__)

        if not class_logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            class_logger.addHandler(handler)
            class_logger.propagate = False

        class_logger.setLevel(level)

    def interpolate(
        self,
        coordinates: List[Tuple[float, float]],
        parameters: Optional[SplineParameters] = None,
        num_points_output_override: Optional[int] = None,
        create_bounds_lines: bool = True,
    ) -> Tuple[LineString, Dict[str, Any]]:
        """
        Interpola coordenadas para criar uma linha suave.

        Parameters
        ----------
        coordinates : List[Tuple[float, float]]
            Lista de coordenadas (longitude, latitude).
        parameters : Optional[SplineParameters]
            Parâmetros de interpolação (usa padrões se None).
        num_points_output_override : Optional[int]
            Sobrescreve o número de pontos de saída.
        create_bounds_lines : bool
            Se deve criar linhas de limite (±1 desvio padrão).

        Returns
        -------
        Tuple[LineString, Dict[str, Any]]
            Linha interpolada e estatísticas do processo.

        Raises
        ------
        TypeError
            Se as coordenadas não estiverem no formato correto.
        ValueError
            Se houver pontos insuficientes para interpolação.
        RuntimeError
            Se a interpolação falhar completamente.
        """
        # Validação de entrada
        self._validate_coordinates(coordinates)

        # Configuração dos parâmetros
        params = self._configure_parameters(
            parameters, num_points_output_override
        )

        # Verificar cache
        cache_key = self._create_cache_key(coordinates, params)
        if cache_key in self._interpolation_cache:
            logger.info('Usando resultado do cache')
            cached_line, cached_stats = self._interpolation_cache[cache_key]
            return LineString(cached_line.coords), dict(cached_stats)

        logger.info(
            f'Interpolando {len(coordinates)} coordenadas: '
            f'método={params.method.value}, pontos_saída={params.num_points_output}'
        )

        try:
            # Processar coordenadas
            coords_array = np.array(coordinates, dtype=float)
            coords_array = self._remove_invalid_coordinates(coords_array)

            x_coords, y_coords = self._preprocess_coordinates(
                coords_array[:, 0], coords_array[:, 1]
            )

            # Verificar pontos suficientes após processamento
            if len(x_coords) < self.min_input_points:
                raise ValueError(
                    f'Pontos insuficientes após processamento: '
                    f'{len(x_coords)} < {self.min_input_points}'
                )

            # Calcular pesos baseados na latitude de referência
            weights = self._calculate_weights(
                y_coords,
                params.reference_latitude or self.default_reference_latitude,
            )

            # Executar interpolação
            x_new, y_new = self._perform_interpolation(
                x_coords, y_coords, weights, params
            )

            # Verificar qualidade e aplicar fallback se necessário
            x_new, y_new, params = self._validate_and_fallback(
                x_new, y_new, x_coords, y_coords, params
            )

            # Criar linha principal e estatísticas
            main_line = LineString(list(zip(x_new, y_new)))

            bounds_data = {}
            if create_bounds_lines:
                bounds_data = self._create_bounds_lines(x_new, y_new, y_coords)

            quality_check = self._check_interpolation_quality(
                x_new, y_new, params.max_curvature_threshold
            )

            statistics = self._compile_statistics(
                coordinates,
                main_line,
                weights,
                params,
                quality_check,
                bounds_data,
            )

            # Atualizar cache
            result = (main_line, statistics)
            self._update_cache(cache_key, result)

            return LineString(main_line.coords), dict(statistics)

        except Exception as e:
            logger.exception(f'Erro na interpolação: {e}')

            # Tentar fallback linear como último recurso
            if params.method != InterpolationMethod.LINEAR:
                return self._fallback_interpolation(
                    coordinates, params, create_bounds_lines
                )

            raise RuntimeError(f'Falha completa na interpolação: {e}') from e

    def _validate_coordinates(
        self, coordinates: List[Tuple[float, float]]
    ) -> None:
        """Valida o formato das coordenadas de entrada."""
        if not isinstance(coordinates, list):
            raise TypeError('coordinates deve ser uma lista')

        if not coordinates:
            raise ValueError('Lista de coordenadas vazia')

        if not all(
            isinstance(c, tuple)
            and len(c) == 2
            and all(isinstance(val, (int, float)) for val in c)
            for c in coordinates
        ):
            raise TypeError(
                'Todas as coordenadas devem ser tuplas (longitude, latitude)'
            )

        if len(coordinates) < self.min_input_points:
            raise ValueError(
                f'Mínimo de {self.min_input_points} coordenadas necessárias, '
                f'recebido: {len(coordinates)}'
            )

    def _configure_parameters(
        self,
        parameters: Optional[SplineParameters],
        num_points_override: Optional[int],
    ) -> SplineParameters:
        """Configura os parâmetros de interpolação."""
        if parameters is None:
            params = SplineParameters(
                method=self.default_method,
                smooth_factor=self.default_smooth_factor,
                degree=self.default_degree,
                reference_latitude=self.default_reference_latitude,
            )
        else:
            params = parameters
            if params.reference_latitude is None:
                params.reference_latitude = self.default_reference_latitude

        if num_points_override is not None:
            params.num_points_output = num_points_override

        return params

    def _remove_invalid_coordinates(self, coords: np.ndarray) -> np.ndarray:
        """Remove coordenadas com NaN ou Inf."""
        if np.any(np.isnan(coords)) or np.any(np.isinf(coords)):
            logger.warning('Removendo coordenadas inválidas (NaN/Inf)')

            valid_mask = ~(
                np.isnan(coords).any(axis=1) | np.isinf(coords).any(axis=1)
            )
            coords = coords[valid_mask]

            if coords.shape[0] < self.min_input_points:
                raise ValueError(
                    f'Pontos insuficientes após remover inválidos: '
                    f'{coords.shape[0]} < {self.min_input_points}'
                )

        return coords

    def _preprocess_coordinates(
        self, x_coords: np.ndarray, y_coords: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Pré-processa coordenadas: remove duplicatas, ordena e verifica espaçamento.

        Parameters
        ----------
        x_coords : np.ndarray
            Coordenadas de longitude.
        y_coords : np.ndarray
            Coordenadas de latitude.

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            Coordenadas processadas (x, y).
        """
        if x_coords.size != y_coords.size:
            raise ValueError('x_coords e y_coords devem ter o mesmo tamanho')

        if x_coords.size == 0:
            return x_coords, y_coords

        # Criar DataFrame para processamento eficiente
        df = pd.DataFrame({'x': x_coords, 'y': y_coords})

        # Ordenar por longitude e remover duplicatas
        df = df.sort_values('x').drop_duplicates(subset=['x'], keep='first')

        x_processed = df['x'].values
        y_processed = df['y'].values

        if len(x_processed) < len(x_coords):
            logger.debug(
                f'Removidas {len(x_coords) - len(x_processed)} '
                f'coordenadas com longitude duplicada'
            )

        # Verificar espaçamento
        if x_processed.size > 1:
            self._check_coordinate_spacing(x_processed)

        return x_processed, y_processed

    def _check_coordinate_spacing(self, x_coords: np.ndarray) -> None:
        """Verifica e registra gaps grandes no espaçamento."""
        dx = np.diff(x_coords)

        if np.any(dx <= 1e-9):
            logger.error('Coordenadas X não são estritamente crescentes')

        median_spacing = np.median(dx)
        if median_spacing > 0:
            large_gaps = np.where(
                dx > self.LARGE_GAP_MULTIPLIER * median_spacing
            )[0]
            if large_gaps.size > 0:
                logger.warning(
                    f'Detectados {large_gaps.size} gaps grandes '
                    f'(>{self.LARGE_GAP_MULTIPLIER}x mediana={median_spacing:.2f}°)'
                )

    def _calculate_weights(
        self, y_coords: np.ndarray, reference_latitude: float
    ) -> np.ndarray:
        """
        Calcula pesos baseados na proximidade à latitude de referência.

        Coordenadas mais próximas da latitude de referência recebem maior peso,
        como se a latitude de referência fosse um "ímã" atraindo a curva.

        Parameters
        ----------
        y_coords : np.ndarray
            Coordenadas de latitude.
        reference_latitude : float
            Latitude de referência.

        Returns
        -------
        np.ndarray
            Array de pesos normalizados.
        """
        if y_coords.size == 0:
            return np.array([])

        logger.debug(
            f'Calculando pesos para lat_ref={reference_latitude:.2f}°'
        )

        # Distância à latitude de referência (com epsilon para evitar divisão por zero)
        distances = np.abs(y_coords - reference_latitude) + 1e-6

        # Peso inversamente proporcional à distância
        weights = 1.0 / distances

        # Normalizar para [0, 1]
        if np.max(weights) > 1e-9:
            weights = weights / np.max(weights)
        else:
            weights = np.ones_like(weights)

        # Suavizar pesos se houver pontos suficientes
        if len(weights) > self.MIN_POINTS_FOR_SMOOTHING:
            weights = gaussian_filter1d(weights, sigma=1.0, mode='reflect')

        # Garantir peso mínimo
        weights = np.maximum(weights, 0.1)

        logger.debug(
            f'Pesos: min={weights.min():.3f}, max={weights.max():.3f}, '
            f'mean={weights.mean():.3f}'
        )

        return weights

    def _perform_interpolation(
        self,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        weights: np.ndarray,
        params: SplineParameters,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Executa a interpolação com o método especificado."""
        method_func = self._interpolation_methods.get(params.method)

        if method_func is None:
            raise ValueError(f'Método {params.method} não implementado')

        # Passar pesos apenas para B-spline
        if params.method == InterpolationMethod.BSPLINE:
            return method_func(x_coords, y_coords, weights, params)
        else:
            return method_func(x_coords, y_coords, None, params)

    def _validate_and_fallback(
        self,
        x_new: np.ndarray,
        y_new: np.ndarray,
        x_orig: np.ndarray,
        y_orig: np.ndarray,
        params: SplineParameters,
    ) -> Tuple[np.ndarray, np.ndarray, SplineParameters]:
        """Valida interpolação e aplica fallback se necessário."""
        quality = self._check_interpolation_quality(
            x_new, y_new, params.max_curvature_threshold
        )

        if (
            not quality['is_valid']
            and params.method != InterpolationMethod.LINEAR
        ):
            logger.warning(
                f"Problemas detectados: {quality['issues']}. "
                f'Aplicando fallback linear'
            )

            fallback_params = SplineParameters(
                method=InterpolationMethod.LINEAR,
                num_points_output=params.num_points_output,
            )

            x_new, y_new = self._interpolate_linear(
                x_orig, y_orig, None, fallback_params
            )

            params.method = InterpolationMethod.LINEAR

        return x_new, y_new, params

    def _interpolate_bspline(
        self,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        weights: Optional[np.ndarray],
        params: SplineParameters,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Interpolação usando B-spline paramétrico."""
        if weights is None:
            weights = np.ones_like(x_coords)
            logger.warning('Usando pesos unitários para B-spline')

        # Verificar grau vs. número de pontos
        if len(x_coords) <= params.degree:
            logger.warning(
                f'Pontos insuficientes para grau {params.degree}. '
                f'Usando interpolação linear'
            )
            return self._interpolate_linear(x_coords, y_coords, None, params)

        # Calcular parâmetro de suavização
        s = self._calculate_smoothing_parameter(
            len(x_coords), weights, y_coords, params.smooth_factor
        )

        # Ajustar grau se necessário
        k = min(params.degree, len(x_coords) - 1)
        k = max(k, 1)

        try:
            # Interpolação paramétrica
            tck, u = interpolate.splprep(
                [x_coords, y_coords], w=weights, s=s, k=k, quiet=1
            )

            u_new = np.linspace(u.min(), u.max(), params.num_points_output)
            x_new, y_new = interpolate.splev(u_new, tck)

            return np.array(x_new), np.array(y_new)

        except Exception as e:
            logger.warning(f'Erro em splprep: {e}. Tentando UnivariateSpline')

            # Fallback para UnivariateSpline
            try:
                if not np.all(np.diff(x_coords) > 0):
                    raise ValueError('x_coords não monotônico')

                spl = interpolate.UnivariateSpline(
                    x_coords, y_coords, w=weights, s=s, k=k
                )

                x_new = np.linspace(
                    x_coords.min(), x_coords.max(), params.num_points_output
                )
                y_new = spl(x_new)

                return x_new, y_new

            except Exception as e2:
                logger.error(f'Erro em UnivariateSpline: {e2}')
                return self._interpolate_linear(
                    x_coords, y_coords, None, params
                )

    def _interpolate_cubic(
        self,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        _: Any,
        params: SplineParameters,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Interpolação usando spline cúbico."""
        if len(x_coords) < 2:
            return x_coords, y_coords

        try:
            cs = interpolate.CubicSpline(
                x_coords, y_coords, extrapolate=params.extrapolate_flag
            )

            x_new = np.linspace(
                x_coords.min(), x_coords.max(), params.num_points_output
            )
            y_new = cs(x_new)

            return x_new, y_new

        except Exception as e:
            logger.warning(f'Erro em CubicSpline: {e}')
            return self._interpolate_linear(x_coords, y_coords, None, params)

    def _interpolate_akima(
        self,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        _: Any,
        params: SplineParameters,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Interpolação usando método Akima."""
        if len(x_coords) < 3:
            logger.warning('Pontos insuficientes para Akima')
            return self._interpolate_linear(x_coords, y_coords, None, params)

        try:
            akima = interpolate.Akima1DInterpolator(x_coords, y_coords)

            x_new = np.linspace(
                x_coords.min(), x_coords.max(), params.num_points_output
            )

            y_new = akima(
                x_new,
                extrapolate=params.extrapolate_flag
                if params.extrapolate_flag
                else None,
            )

            return x_new, y_new

        except Exception as e:
            logger.warning(f'Erro em Akima: {e}')
            return self._interpolate_linear(x_coords, y_coords, None, params)

    def _interpolate_pchip(
        self,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        _: Any,
        params: SplineParameters,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Interpolação usando PCHIP (Piecewise Cubic Hermite)."""
        if len(x_coords) < 2:
            return x_coords, y_coords

        try:
            pchip = interpolate.PchipInterpolator(
                x_coords, y_coords, extrapolate=params.extrapolate_flag
            )

            x_new = np.linspace(
                x_coords.min(), x_coords.max(), params.num_points_output
            )
            y_new = pchip(x_new)

            return x_new, y_new

        except Exception as e:
            logger.warning(f'Erro em PCHIP: {e}')
            return self._interpolate_linear(x_coords, y_coords, None, params)

    def _interpolate_linear(
        self,
        x_coords: np.ndarray,
        y_coords: np.ndarray,
        _: Any,
        params: SplineParameters,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Interpolação linear simples."""
        if len(x_coords) < 2:
            return x_coords, y_coords

        try:
            f = interpolate.interp1d(
                x_coords,
                y_coords,
                kind='linear',
                fill_value='extrapolate'
                if params.extrapolate_flag
                else np.nan,
                bounds_error=False,
            )

            x_new = np.linspace(
                x_coords.min(), x_coords.max(), params.num_points_output
            )
            y_new = f(x_new)

            return x_new, y_new

        except Exception as e:
            logger.error(f'Erro crítico em interpolação linear: {e}')

            # Retorno de emergência
            x_out = np.linspace(
                x_coords.min() if x_coords.size > 0 else 0,
                x_coords.max() if x_coords.size > 0 else 1,
                params.num_points_output,
            )
            y_out = np.full(params.num_points_output, np.nan)

            return x_out, y_out

    def _calculate_smoothing_parameter(
        self,
        n_points: int,
        weights: np.ndarray,
        y_coords: np.ndarray,
        smooth_factor: Union[str, float],
    ) -> float:
        """Calcula o parâmetro de suavização 's' para B-spline."""
        if n_points <= 1:
            return 0.0

        if isinstance(smooth_factor, str):
            if smooth_factor == 'auto':
                s = float(n_points)
                logger.debug(f"Suavização 'auto': s={s:.3f}")
            elif smooth_factor in self.SMOOTH_PRESETS:
                factor = self.SMOOTH_PRESETS[smooth_factor]
                s = n_points * factor
                logger.debug(f"Suavização '{smooth_factor}': s={s:.3f}")
            else:
                logger.warning(
                    f"Fator '{smooth_factor}' não reconhecido. Usando 'auto'"
                )
                s = float(n_points)
        elif isinstance(smooth_factor, (int, float)):
            s = float(smooth_factor)
            logger.debug(f'Suavização numérica: s={s:.3f}')
        else:
            logger.warning("Tipo de smooth_factor inválido. Usando 'auto'")
            s = float(n_points)

        return max(0.0, s)

    def _check_interpolation_quality(
        self,
        x_new: np.ndarray,
        y_new: np.ndarray,
        max_curvature: Optional[float],
    ) -> Dict[str, Any]:
        """
        Verifica a qualidade da interpolação.

        Parameters
        ----------
        x_new : np.ndarray
            Coordenadas X interpoladas.
        y_new : np.ndarray
            Coordenadas Y interpoladas.
        max_curvature : Optional[float]
            Limiar máximo de curvatura aceitável.

        Returns
        -------
        Dict[str, Any]
            Relatório de qualidade com métricas e problemas detectados.
        """
        quality: Dict[str, Any] = {
            'is_valid': True,
            'issues': [],
            'metrics': {},
        }

        # Verificações básicas
        if x_new.size == 0 or y_new.size == 0:
            quality['is_valid'] = False
            quality['issues'].append('Arrays vazios')
            return quality

        # Verificar NaN e Inf
        nan_count_x = np.sum(np.isnan(x_new))
        nan_count_y = np.sum(np.isnan(y_new))
        if nan_count_x > 0 or nan_count_y > 0:
            quality['issues'].append(
                f'NaNs detectados (x:{nan_count_x}, y:{nan_count_y})'
            )

        if np.any(np.isinf(x_new)) or np.any(np.isinf(y_new)):
            quality['is_valid'] = False
            quality['issues'].append('Valores infinitos detectados')

        # Verificar monotonicidade de X
        if x_new.size > 1 and not np.all(np.diff(x_new) > 1e-9):
            quality['is_valid'] = False
            quality['issues'].append('X não é monotonicamente crescente')

        # Análises avançadas (se houver pontos suficientes)
        if x_new.size >= 3:
            # Calcular curvatura
            curvatures = self._calculate_curvature(x_new, y_new)
            max_abs_curvature = (
                np.max(np.abs(curvatures)) if curvatures.size > 0 else 0.0
            )
            quality['metrics']['max_absolute_curvature'] = float(
                max_abs_curvature
            )

            if max_curvature is not None and max_abs_curvature > max_curvature:
                quality['issues'].append(
                    f'Curvatura excessiva: {max_abs_curvature:.4f} > {max_curvature}'
                )

            # Detectar oscilações
            oscillation_ratio = self._detect_oscillations(y_new)
            quality['metrics']['oscillation_ratio'] = oscillation_ratio

            if oscillation_ratio > self.MAX_OSCILLATION_RATIO:
                quality['issues'].append(
                    f'Oscilações excessivas: {oscillation_ratio:.2%}'
                )

        # Verificar saltos em latitude
        if y_new.size > 1:
            max_lat_gap = np.max(np.abs(np.diff(y_new)))
            quality['metrics']['max_latitude_gap'] = float(max_lat_gap)

            if max_lat_gap > self.MAX_LATITUDE_JUMP:
                quality['issues'].append(
                    f'Salto de latitude: {max_lat_gap:.2f}° > {self.MAX_LATITUDE_JUMP}°'
                )

        # Determinar validade final
        if quality['issues']:
            quality['is_valid'] = False

        return quality

    def _calculate_curvature(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """
        Calcula a curvatura de uma curva paramétrica.

        A curvatura mede o quanto a curva se desvia de uma linha reta,
        como o raio de curvatura de uma estrada.

        Parameters
        ----------
        x : np.ndarray
            Coordenadas X.
        y : np.ndarray
            Coordenadas Y.

        Returns
        -------
        np.ndarray
            Valores de curvatura em cada ponto.
        """
        if len(x) < 3:
            return np.zeros(len(x))

        # Primeiras derivadas
        dx = np.gradient(x)
        dy = np.gradient(y)

        # Segundas derivadas
        d2x = np.gradient(dx)
        d2y = np.gradient(dy)

        # Fórmula da curvatura: |x'y'' - y'x''| / (x'^2 + y'^2)^(3/2)
        numerator = np.abs(dx * d2y - dy * d2x)
        denominator = np.power(dx**2 + dy**2, 1.5) + 1e-9

        return numerator / denominator

    def _detect_oscillations(self, y: np.ndarray) -> float:
        """
        Detecta oscilações na coordenada Y.

        Conta mudanças de direção como proporção do total de segmentos.

        Parameters
        ----------
        y : np.ndarray
            Valores de Y.

        Returns
        -------
        float
            Razão de oscilação (0 a 1).
        """
        if len(y) < 3:
            return 0.0

        # Calcular mudanças de sinal na derivada
        dy = np.diff(y)
        sign_changes = np.diff(np.sign(dy[dy != 0]))

        # Contar oscilações (mudanças de sinal = ±2)
        oscillations = np.sum(np.abs(sign_changes) == 2)

        # Normalizar pelo número de segmentos
        total_segments = len(dy[dy != 0]) - 1

        if total_segments <= 0:
            return 0.0

        return oscillations / total_segments

    def _create_bounds_lines(
        self, x_new: np.ndarray, y_new: np.ndarray, y_original: np.ndarray
    ) -> Dict[str, Union[LineString, float]]:
        """
        Cria linhas de limite baseadas no desvio padrão.

        Parameters
        ----------
        x_new : np.ndarray
            Coordenadas X interpoladas.
        y_new : np.ndarray
            Coordenadas Y interpoladas.
        y_original : np.ndarray
            Coordenadas Y originais.

        Returns
        -------
        Dict[str, Union[LineString, float]]
            Linhas de limite e desvio padrão.
        """
        std_dev = np.std(y_original) if y_original.size >= 2 else 0.0

        return {
            'plus_std_line': LineString(list(zip(x_new, y_new + std_dev))),
            'minus_std_line': LineString(list(zip(x_new, y_new - std_dev))),
            'std_dev_latitude': float(std_dev),
        }

    def _compile_statistics(
        self,
        original_coords: List[Tuple[float, float]],
        interpolated_line: LineString,
        weights: np.ndarray,
        params: SplineParameters,
        quality: Dict[str, Any],
        bounds_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compila estatísticas completas da interpolação."""
        input_array = np.array(original_coords)
        interp_array = np.array(interpolated_line.coords)

        statistics: Dict[str, Any] = {
            'interpolation_parameters': {
                'method': params.method.value,
                'smooth_factor': params.smooth_factor,
                'degree': params.degree,
                'num_points_output': params.num_points_output,
                'reference_latitude': params.reference_latitude,
            },
            'method_used': params.method.value,
            'timestamp_utc': datetime.utcnow().isoformat() + 'Z',
            'input_points_count': len(original_coords),
            'output_points_count': len(interp_array),
            'quality_assessment': quality,
            'input_longitude_range': (
                float(input_array[:, 0].min()),
                float(input_array[:, 0].max()),
            )
            if input_array.size > 0
            else (np.nan, np.nan),
            'input_latitude_range': (
                float(input_array[:, 1].min()),
                float(input_array[:, 1].max()),
            )
            if input_array.size > 0
            else (np.nan, np.nan),
            'output_longitude_range': (
                float(interp_array[:, 0].min()),
                float(interp_array[:, 0].max()),
            )
            if interp_array.size > 0
            else (np.nan, np.nan),
            'output_latitude_range': (
                float(interp_array[:, 1].min()),
                float(interp_array[:, 1].max()),
            )
            if interp_array.size > 0
            else (np.nan, np.nan),
        }

        # Estatísticas de pesos
        if weights is not None and weights.size > 0:
            statistics['weights_stats'] = {
                'min': float(weights.min()),
                'max': float(weights.max()),
                'mean': float(weights.mean()),
                'std': float(weights.std()),
            }
        else:
            statistics['weights_stats'] = 'Não aplicável'

        # Desvio padrão da latitude
        if bounds_data:
            statistics['latitude_std_dev'] = bounds_data.get(
                'std_dev_latitude', np.nan
            )

        # Métricas de ajuste (se aplicável)
        if (
            params.method != InterpolationMethod.BSPLINE
            and input_array.shape[0] >= 2
            and interp_array.shape[0] >= 2
        ):

            try:
                self._add_fit_metrics(statistics, input_array, interp_array)
            except Exception as e:
                logger.debug(f'Erro ao calcular métricas de ajuste: {e}')
                statistics['fit_metrics_error'] = str(e)

        return statistics

    def _add_fit_metrics(
        self,
        statistics: Dict[str, Any],
        input_array: np.ndarray,
        interp_array: np.ndarray,
    ) -> None:
        """Adiciona métricas de qualidade do ajuste."""
        # Interpolar pontos originais nas posições da linha interpolada
        f_orig = interpolate.interp1d(
            input_array[:, 0],
            input_array[:, 1],
            kind='linear',
            fill_value='extrapolate',
            bounds_error=False,
        )

        y_orig_at_interp = f_orig(interp_array[:, 0])

        # Filtrar valores válidos
        valid_mask = ~np.isnan(y_orig_at_interp) & ~np.isnan(
            interp_array[:, 1]
        )

        if np.sum(valid_mask) >= 2:
            # RMSE
            rmse = np.sqrt(
                np.mean(
                    (
                        interp_array[valid_mask, 1]
                        - y_orig_at_interp[valid_mask]
                    )
                    ** 2
                )
            )
            statistics['rmse'] = float(rmse)

            # R²
            r_value, _ = stats.pearsonr(
                interp_array[valid_mask, 1], y_orig_at_interp[valid_mask]
            )
            statistics['r_squared'] = float(r_value**2)

    def _fallback_interpolation(
        self,
        coordinates: List[Tuple[float, float]],
        params: SplineParameters,
        create_bounds: bool,
    ) -> Tuple[LineString, Dict[str, Any]]:
        """Interpolação de fallback usando método linear."""
        logger.warning('Aplicando interpolação linear de fallback')

        try:
            coords_array = np.array(coordinates)
            x_coords, y_coords = self._preprocess_coordinates(
                coords_array[:, 0], coords_array[:, 1]
            )

            if len(x_coords) < self.min_input_points:
                raise ValueError(f'Pontos insuficientes: {len(x_coords)}')

            linear_params = SplineParameters(
                method=InterpolationMethod.LINEAR,
                num_points_output=params.num_points_output,
            )

            x_new, y_new = self._interpolate_linear(
                x_coords, y_coords, None, linear_params
            )

            main_line = LineString(list(zip(x_new, y_new)))

            quality = self._check_interpolation_quality(
                x_new, y_new, params.max_curvature_threshold
            )

            bounds_data = {}
            if create_bounds:
                bounds_data = self._create_bounds_lines(x_new, y_new, y_coords)

            statistics = self._compile_statistics(
                coordinates,
                main_line,
                np.ones_like(y_coords),
                linear_params,
                quality,
                bounds_data,
            )

            statistics['fallback_reason'] = 'Erro no método principal'

            return main_line, statistics

        except Exception as e:
            logger.error(f'Falha no fallback linear: {e}')
            raise

    def _create_cache_key(
        self, coordinates: List[Tuple[float, float]], params: SplineParameters
    ) -> str:
        """Cria chave única para cache."""
        # Hash das coordenadas
        coord_str = ';'.join(
            f'{x:.4f},{y:.4f}' for x, y in sorted(coordinates)
        )
        coord_hash = hashlib.md5(coord_str.encode()).hexdigest()

        # Combinar com parâmetros
        param_str = '_'.join(str(p) for p in params.to_cache_key())

        return f'{coord_hash}_{param_str}'

    def _update_cache(
        self, key: str, result: Tuple[LineString, Dict[str, Any]]
    ) -> None:
        """Atualiza o cache com gerenciamento de tamanho."""
        if len(self._interpolation_cache) >= self._cache_size:
            # Remover item mais antigo (FIFO)
            oldest_key = next(iter(self._interpolation_cache))
            del self._interpolation_cache[oldest_key]
            logger.debug('Cache cheio, removido item mais antigo')

        self._interpolation_cache[key] = result
        logger.debug('Resultado armazenado no cache')

    def validate_interpolation(
        self,
        original_coordinates: List[Tuple[float, float]],
        interpolated_line: LineString,
        max_deviation: float = 2.0,
        min_r_squared: float = 0.7,
    ) -> Dict[str, Any]:
        """
        Valida a linha interpolada contra os pontos originais.

        Parameters
        ----------
        original_coordinates : List[Tuple[float, float]]
            Coordenadas originais.
        interpolated_line : LineString
            Linha interpolada.
        max_deviation : float, optional
            Desvio máximo aceitável (default: 2.0).
        min_r_squared : float, optional
            R² mínimo aceitável (default: 0.7).

        Returns
        -------
        Dict[str, Any]
            Resultado da validação com métricas.
        """
        if not interpolated_line.coords:
            return {'is_valid': False, 'reason': 'Linha interpolada vazia'}

        # Extrair coordenadas
        orig_coords = np.array(original_coordinates)
        interp_coords = np.array(interpolated_line.coords)

        results: Dict[str, Any] = {
            'is_valid': True,
            'issues': [],
            'metrics': {},
        }

        # Verificar cobertura do range
        if (
            interp_coords[:, 0].min() > orig_coords[:, 0].min()
            or interp_coords[:, 0].max() < orig_coords[:, 0].max()
        ):
            results['issues'].append(
                'Linha não cobre range completo de longitude'
            )

        try:
            # Interpolar linha nos pontos originais
            f_interp = interpolate.interp1d(
                interp_coords[:, 0],
                interp_coords[:, 1],
                kind='linear',
                bounds_error=False,
                fill_value=np.nan,
            )

            y_interpolated = f_interp(orig_coords[:, 0])

            # Calcular resíduos
            residuals = orig_coords[:, 1] - y_interpolated
            valid_residuals = residuals[~np.isnan(residuals)]

            if valid_residuals.size > 0:
                # Métricas de desvio
                mean_abs_dev = np.mean(np.abs(valid_residuals))
                max_abs_dev = np.max(np.abs(valid_residuals))

                results['metrics']['mean_absolute_deviation'] = float(
                    mean_abs_dev
                )
                results['metrics']['max_absolute_deviation'] = float(
                    max_abs_dev
                )

                if max_abs_dev > max_deviation:
                    results['is_valid'] = False
                    results['issues'].append(
                        f'Desvio máximo ({max_abs_dev:.2f}°) > limite ({max_deviation}°)'
                    )

            # Calcular R² se houver pontos suficientes
            if valid_residuals.size >= 2:
                valid_mask = ~np.isnan(y_interpolated)
                if np.sum(valid_mask) >= 2:
                    r_value, _ = stats.pearsonr(
                        orig_coords[valid_mask, 1], y_interpolated[valid_mask]
                    )
                    r_squared = r_value**2

                    results['metrics']['r_squared'] = float(r_squared)

                    if r_squared < min_r_squared:
                        results['is_valid'] = False
                        results['issues'].append(
                            f'R² ({r_squared:.3f}) < limite ({min_r_squared})'
                        )

        except Exception as e:
            results['is_valid'] = False
            results['issues'].append(f'Erro na validação: {str(e)}')

        return results

    def __repr__(self) -> str:
        """Representação em string da instância."""
        return (
            f'<SplineInterpolator('
            f'method={self.default_method.value}, '
            f'smooth={self.default_smooth_factor}, '
            f'min_points={self.min_input_points})>'
        )
