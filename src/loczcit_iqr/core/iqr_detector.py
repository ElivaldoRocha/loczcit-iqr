"""
loczcit_iqr/core/iqr_detector.py

Módulo para detecção de outliers usando o método IQR (Intervalo Interquartílico).

Este módulo implementa a detecção de valores discrepantes em coordenadas geográficas,
utilizando o método estatístico do Intervalo Interquartílico (IQR).
"""

import logging
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

# Importações opcionais com fallback
SCIPY_AVAILABLE = False
try:
    from scipy import stats as scipy_stats
    from scipy.spatial.distance import cdist

    SCIPY_AVAILABLE = True
except ImportError:
    scipy_stats = None
    cdist = None

# Importação do validador com fallback
VALIDATOR_AVAILABLE = False
try:
    from loczcit_iqr.utils import validate_iqr_constant

    VALIDATOR_AVAILABLE = True
except ImportError:

    def validate_iqr_constant(
        constant: float, default_if_invalid: float = 1.5
    ) -> float:
        """Fallback para validação da constante IQR."""
        if not isinstance(constant, (int, float)) or constant <= 0:
            return default_if_invalid
        return float(constant)


# Configuração do logger do módulo
logger = logging.getLogger(__name__)


class IQRDetector:
    """
    Detector de outliers usando o método IQR (Intervalo Interquartílico).

    Esta classe identifica valores discrepantes em dados de coordenadas geográficas,
    analisando a distribuição estatística em uma dimensão específica (latitude ou longitude).

    Attributes
    ----------
    constant : float
        Multiplicador do IQR para definir os limites de detecção.
        Valores típicos: 1.5 (padrão), 0.75 (restritivo), 3.0 (permissivo).

    Examples
    --------
    >>> detector = IQRDetector(constant=1.5)
    >>> coords = [(10.0, 20.0), (10.1, 20.1), (10.2, 50.0)]
    >>> valid, outliers, stats = detector.detect_outliers(coords)
    """

    def __init__(
        self, constant: float = 1.5, log_level: Union[int, str] = logging.INFO
    ) -> None:
        """
        Inicializa o detector IQR.

        Parameters
        ----------
        constant : float, optional
            Constante multiplicativa para o IQR (default: 1.5).
        log_level : Union[int, str], optional
            Nível de logging (default: logging.INFO).
        """
        self._setup_logging(log_level)
        self.constant = self._validate_constant(constant)

        logger.info(f'IQRDetector inicializado com constante: {self.constant}')

        if not SCIPY_AVAILABLE:
            logger.warning(
                'SciPy não disponível. Funcionalidades estatísticas avançadas '
                '(skewness, kurtosis, validação por distância) estarão limitadas.'
            )

    def _setup_logging(self, level: Union[int, str]) -> None:
        """Configura o sistema de logging para a instância."""
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

    def _validate_constant(self, constant: float) -> float:
        """Valida e retorna a constante IQR."""
        if VALIDATOR_AVAILABLE:
            return validate_iqr_constant(constant)

        # Validação fallback
        if isinstance(constant, (int, float)) and constant > 0:
            return float(constant)

        logger.warning(
            f'Constante IQR inválida: {constant}. Usando padrão: 1.5'
        )
        return 1.5

    def detect_outliers(
        self, coordinates: List[Tuple[float, float]], coordinate_index: int = 1
    ) -> Tuple[
        List[Tuple[float, float]], List[Tuple[float, float]], Dict[str, Any]
    ]:
        """
        Detecta outliers nas coordenadas usando o método IQR.

        Parameters
        ----------
        coordinates : List[Tuple[float, float]]
            Lista de coordenadas (longitude, latitude).
        coordinate_index : int, optional
            Índice para análise: 0 (longitude) ou 1 (latitude).
            Default: 1.

        Returns
        -------
        Tuple[List[Tuple[float, float]], List[Tuple[float, float]], Dict[str, Any]]
            (coordenadas_válidas, coordenadas_outliers, estatísticas)

        Raises
        ------
        TypeError
            Se coordinates não for uma lista.
        ValueError
            Se as coordenadas estiverem em formato inválido.
        """
        # Validação de entrada
        self._validate_input(coordinates, coordinate_index)

        if not coordinates:
            logger.warning('Lista de coordenadas vazia.')
            return [], [], self._empty_statistics()

        logger.info(
            f'Detectando outliers em {len(coordinates)} coordenadas '
            f"(analisando {'longitude' if coordinate_index == 0 else 'latitude'})"
        )

        # Extração dos valores para análise
        values = self._extract_values(coordinates, coordinate_index)

        # Cálculo dos quartis e limites
        q1, q2, q3, iqr, lower_limit, upper_limit = self._calculate_iqr_limits(
            values
        )

        # Classificação das coordenadas
        valid_coords, outlier_coords = self._classify_coordinates(
            coordinates, values, lower_limit, upper_limit
        )

        # Cálculo das estatísticas
        statistics = self._calculate_statistics(
            values,
            q1,
            q2,
            q3,
            iqr,
            lower_limit,
            upper_limit,
            len(valid_coords),
            len(outlier_coords),
        )

        logger.info(
            f'Detecção concluída: {len(valid_coords)} válidas, '
            f'{len(outlier_coords)} outliers'
        )

        return valid_coords, outlier_coords, statistics

    def _validate_input(
        self, coordinates: List[Tuple[float, float]], coordinate_index: int
    ) -> None:
        """Valida os parâmetros de entrada."""
        if not isinstance(coordinates, list):
            raise TypeError('coordinates deve ser uma lista')

        if coordinate_index not in [0, 1]:
            raise ValueError('coordinate_index deve ser 0 ou 1')

        if coordinates and not all(
            isinstance(c, tuple)
            and len(c) == 2
            and all(isinstance(val, (int, float)) for val in c)
            for c in coordinates
        ):
            raise ValueError(
                'Todas as coordenadas devem ser tuplas de dois números'
            )

    def _extract_values(
        self, coordinates: List[Tuple[float, float]], coordinate_index: int
    ) -> np.ndarray:
        """Extrai os valores da dimensão especificada."""
        try:
            return np.array(
                [coord[coordinate_index] for coord in coordinates], dtype=float
            )
        except (IndexError, TypeError) as e:
            logger.error(f'Erro ao extrair valores: {e}')
            raise ValueError('Erro ao processar coordenadas') from e

    def _calculate_iqr_limits(
        self, values: np.ndarray
    ) -> Tuple[float, float, float, float, float, float]:
        """Calcula quartis e limites IQR."""
        q1 = np.percentile(values, 25)
        q2 = np.percentile(values, 50)
        q3 = np.percentile(values, 75)
        iqr = q3 - q1

        # Tratamento para IQR zero ou muito pequeno
        if np.abs(iqr) < 1e-9:
            lower_limit, upper_limit = self._handle_zero_iqr(values, q2)
        else:
            lower_limit = q1 - (self.constant * iqr)
            upper_limit = q3 + (self.constant * iqr)

        logger.debug(
            f'Q1={q1:.2f}, Q2={q2:.2f}, Q3={q3:.2f}, IQR={iqr:.2f}, '
            f'Limites: [{lower_limit:.2f}, {upper_limit:.2f}]'
        )

        return q1, q2, q3, iqr, lower_limit, upper_limit

    def _handle_zero_iqr(
        self, values: np.ndarray, median: float
    ) -> Tuple[float, float]:
        """Trata casos onde IQR é zero ou muito pequeno."""
        logger.warning('IQR próximo de zero. Dados com baixa variabilidade.')

        if np.all(values == values[0]):
            # Todos os valores são idênticos
            return values[0], values[0]

        # Usa desvio padrão como fallback
        std_dev = np.std(values)
        epsilon = std_dev * 0.1 if std_dev > 1e-9 else 0.01

        lower_limit = median - epsilon
        upper_limit = median + epsilon

        logger.info(
            f'Usando limites baseados em desvio padrão: '
            f'[{lower_limit:.3f}, {upper_limit:.3f}]'
        )

        return lower_limit, upper_limit

    def _classify_coordinates(
        self,
        coordinates: List[Tuple[float, float]],
        values: np.ndarray,
        lower_limit: float,
        upper_limit: float,
    ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        """Classifica coordenadas em válidas e outliers."""
        valid_coords = []
        outlier_coords = []

        for i, (coord, value) in enumerate(zip(coordinates, values)):
            if lower_limit <= value <= upper_limit:
                valid_coords.append(coord)
            else:
                outlier_coords.append(coord)
                logger.debug(
                    f'Outlier detectado: {coord} '
                    f'(valor {value:.2f} fora de [{lower_limit:.2f}, {upper_limit:.2f}])'
                )

        return valid_coords, outlier_coords

    def analyze_coordinate_distribution(
        self, coordinates: List[Tuple[float, float]], coordinate_index: int = 1
    ) -> Dict[str, Any]:
        """
        Analisa a distribuição estatística das coordenadas.

        Parameters
        ----------
        coordinates : List[Tuple[float, float]]
            Lista de coordenadas para análise.
        coordinate_index : int, optional
            Índice da dimensão a analisar (default: 1).

        Returns
        -------
        Dict[str, Any]
            Dicionário com estatísticas descritivas.
        """
        if not coordinates:
            return self._empty_statistics()

        if coordinate_index not in [0, 1]:
            raise ValueError('coordinate_index deve ser 0 ou 1')

        values = self._extract_values(coordinates, coordinate_index)

        if values.size == 0:
            return self._empty_statistics()

        # Cálculo das estatísticas básicas
        q1, q2, q3 = np.percentile(values, [25, 50, 75])
        iqr = q3 - q1

        stats = {
            'count': len(values),
            'mean': float(np.mean(values)),
            'median': float(q2),
            'std': float(np.std(values)),
            'variance': float(np.var(values)),
            'min': float(np.min(values)),
            'max': float(np.max(values)),
            'range': float(np.ptp(values)),
            'q1': float(q1),
            'q3': float(q3),
            'iqr': float(iqr),
            'outlier_lower_limit': float(q1 - (self.constant * iqr)),
            'outlier_upper_limit': float(q3 + (self.constant * iqr)),
            'iqr_constant': self.constant,
        }

        # Estatísticas avançadas (se SciPy disponível)
        if SCIPY_AVAILABLE:
            try:
                stats['skewness'] = float(scipy_stats.skew(values))
                stats['kurtosis'] = float(scipy_stats.kurtosis(values))
            except Exception as e:
                logger.warning(f'Erro ao calcular estatísticas avançadas: {e}')
                stats['skewness'] = None
                stats['kurtosis'] = None
        else:
            stats['skewness'] = None
            stats['kurtosis'] = None

        return stats

    def test_different_constants(
        self,
        coordinates: List[Tuple[float, float]],
        constants_to_test: Optional[List[float]] = None,
        coordinate_index: int = 1,
    ) -> Dict[float, Dict[str, Any]]:
        """
        Testa diferentes constantes IQR para análise de sensibilidade.

        Parameters
        ----------
        coordinates : List[Tuple[float, float]]
            Coordenadas para teste.
        constants_to_test : List[float], optional
            Lista de constantes a testar.
        coordinate_index : int, optional
            Índice da dimensão (default: 1).

        Returns
        -------
        Dict[float, Dict[str, Any]]
            Resultados para cada constante testada.
        """
        if constants_to_test is None:
            constants_to_test = [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]

        if not coordinates:
            logger.warning('Nenhuma coordenada fornecida para teste.')
            return {}

        results = {}

        for const in constants_to_test:
            validated_const = self._validate_constant(const)

            if validated_const != const:
                logger.warning(
                    f'Constante {const} ajustada para {validated_const}'
                )

            # Cria detector temporário com a constante de teste
            temp_detector = IQRDetector(
                constant=validated_const, log_level=logger.level
            )

            _, _, stats = temp_detector.detect_outliers(
                coordinates, coordinate_index
            )

            results[validated_const] = {
                'valid_count': stats['valid_coordinates'],
                'outlier_count': stats['outlier_coordinates'],
                'outlier_percentage': stats['outlier_percentage'],
                'lower_limit': stats['lower_limit'],
                'upper_limit': stats['upper_limit'],
            }

        return results

    def get_optimal_constant(
        self,
        coordinates: List[Tuple[float, float]],
        target_outlier_percentage: float = 5.0,
        coordinate_index: int = 1,
        search_range: Tuple[float, float, float] = (0.1, 3.1, 0.1),
    ) -> float:
        """
        Encontra a constante IQR que resulta no percentual alvo de outliers.

        Parameters
        ----------
        coordinates : List[Tuple[float, float]]
            Coordenadas para análise.
        target_outlier_percentage : float, optional
            Percentual alvo de outliers (default: 5.0).
        coordinate_index : int, optional
            Índice da dimensão (default: 1).
        search_range : Tuple[float, float, float], optional
            Range de busca (início, fim, passo).

        Returns
        -------
        float
            Constante ótima encontrada.
        """
        if not coordinates:
            logger.warning('Sem coordenadas para otimização.')
            return self.constant

        if not 0.0 <= target_outlier_percentage <= 100.0:
            raise ValueError(
                'target_outlier_percentage deve estar entre 0 e 100'
            )

        logger.info(
            f'Buscando constante IQR para ~{target_outlier_percentage}% de outliers'
        )

        test_constants = np.arange(*search_range)
        best_constant = self.constant
        best_difference = float('inf')

        for const in test_constants:
            validated_const = self._validate_constant(const)

            temp_detector = IQRDetector(
                constant=validated_const, log_level=logger.level
            )

            _, outliers, _ = temp_detector.detect_outliers(
                coordinates, coordinate_index
            )

            outlier_percentage = (len(outliers) / len(coordinates)) * 100
            difference = abs(outlier_percentage - target_outlier_percentage)

            if difference < best_difference:
                best_difference = difference
                best_constant = validated_const

            # Parada antecipada se muito próximo
            if difference < 0.1:
                break

        logger.info(
            f'Constante ótima: {best_constant:.2f} '
            f'(diferença: {best_difference:.2f}%)'
        )

        return best_constant

    def validate_outliers(
        self,
        all_coordinates: List[Tuple[float, float]],
        detected_outliers: List[Tuple[float, float]],
        max_distance_threshold: Optional[float] = None,
    ) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        """
        Valida outliers detectados usando critérios adicionais.

        Parameters
        ----------
        all_coordinates : List[Tuple[float, float]]
            Todas as coordenadas originais.
        detected_outliers : List[Tuple[float, float]]
            Outliers detectados para validação.
        max_distance_threshold : float, optional
            Distância máxima (em graus) para considerar um outlier como válido.

        Returns
        -------
        Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]
            (outliers_confirmados, falsos_positivos)
        """
        if not detected_outliers or not all_coordinates:
            return [], []

        # Calcula coordenadas válidas
        outlier_set = set(map(tuple, detected_outliers))
        valid_coords = [
            coord
            for coord in all_coordinates
            if tuple(coord) not in outlier_set
        ]

        confirmed_outliers = []
        false_positives = []

        for outlier in detected_outliers:
            is_true_outlier = True

            # Validação por distância (se threshold fornecido e SciPy disponível)
            if (
                max_distance_threshold is not None
                and valid_coords
                and SCIPY_AVAILABLE
            ):

                min_distance = self._calculate_min_distance(
                    outlier, valid_coords
                )

                if (
                    min_distance is not None
                    and min_distance <= max_distance_threshold
                ):
                    is_true_outlier = False
                    logger.debug(
                        f'Outlier {outlier} reclassificado '
                        f'(distância {min_distance:.2f}° <= {max_distance_threshold}°)'
                    )

            if is_true_outlier:
                confirmed_outliers.append(outlier)
            else:
                false_positives.append(outlier)

        logger.info(
            f'Validação: {len(confirmed_outliers)} confirmados, '
            f'{len(false_positives)} reclassificados'
        )

        return confirmed_outliers, false_positives

    def _calculate_min_distance(
        self,
        target: Tuple[float, float],
        coordinates: List[Tuple[float, float]],
    ) -> Optional[float]:
        """Calcula a distância euclidiana mínima."""
        if not SCIPY_AVAILABLE or not coordinates:
            return None

        try:
            target_array = np.array([target])
            coords_array = np.array(coordinates)

            distances = cdist(target_array, coords_array, metric='euclidean')
            return float(np.min(distances))

        except Exception as e:
            logger.error(f'Erro ao calcular distância: {e}')
            return None

    def _calculate_statistics(
        self,
        values: np.ndarray,
        q1: float,
        q2: float,
        q3: float,
        iqr: float,
        lower_limit: float,
        upper_limit: float,
        valid_count: int,
        outlier_count: int,
    ) -> Dict[str, Any]:
        """Compila estatísticas completas da análise."""
        total_count = len(values)

        stats = {
            'total_coordinates': total_count,
            'valid_coordinates': valid_count,
            'outlier_coordinates': outlier_count,
            'outlier_percentage': (
                (outlier_count / total_count) * 100 if total_count > 0 else 0.0
            ),
            'mean': float(np.mean(values)) if values.size > 0 else np.nan,
            'median': float(q2),
            'std': float(np.std(values)) if values.size > 1 else np.nan,
            'min': float(np.min(values)) if values.size > 0 else np.nan,
            'max': float(np.max(values)) if values.size > 0 else np.nan,
            'range': float(np.ptp(values)) if values.size > 0 else 0.0,
            'q1': float(q1),
            'q3': float(q3),
            'iqr': float(iqr),
            'lower_limit': float(lower_limit),
            'upper_limit': float(upper_limit),
            'iqr_constant': self.constant,
        }

        # Coeficiente de variação
        if values.size > 0 and stats['mean'] != 0:
            stats['coefficient_variation'] = (
                stats['std'] / abs(stats['mean'])
            ) * 100
        else:
            stats['coefficient_variation'] = np.nan

        # Razão IQR/Range
        if stats['range'] > 0 and not np.isnan(iqr):
            stats['iqr_to_range_ratio'] = iqr / stats['range']
        else:
            stats['iqr_to_range_ratio'] = np.nan

        return stats

    def _empty_statistics(self) -> Dict[str, Any]:
        """Retorna estrutura de estatísticas vazia."""
        return {
            'total_coordinates': 0,
            'valid_coordinates': 0,
            'outlier_coordinates': 0,
            'outlier_percentage': 0.0,
            'mean': np.nan,
            'median': np.nan,
            'std': np.nan,
            'min': np.nan,
            'max': np.nan,
            'range': np.nan,
            'q1': np.nan,
            'q3': np.nan,
            'iqr': np.nan,
            'lower_limit': np.nan,
            'upper_limit': np.nan,
            'iqr_constant': self.constant,
            'coefficient_variation': np.nan,
            'iqr_to_range_ratio': np.nan,
            'skewness': None,
            'kurtosis': None,
        }

    def __repr__(self) -> str:
        """Representação em string da instância."""
        return f'<IQRDetector(constant={self.constant})>'
