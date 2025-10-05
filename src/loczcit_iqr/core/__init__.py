"""Core functionality for loczcit_iqr."""

# Importar o que existe no data_loader.py
# Importar climatologia
from .climatologia import (  # Funções regionais
    ClimatologiaZCIT,
    analise_zcit_rapida,
    calcular_climatologia_personalizada,
    calcular_climatologia_zcit_completa,
    carregar_climatologia,
    climatologia_amazonia_oriental,
    climatologia_atlantico_tropical,
    climatologia_nordeste_brasileiro,
    comparar_com_climatologia_cientifica,
    executar_analise_limpa,
    obter_climatologia_zcit_rapida,
    salvar_climatologia,
)
from .data_loader import NOAADataLoader, load_olr_data

# Importar o que existe no iqr_detector.py
from .iqr_detector import IQRDetector

# Importar o que existe no processor.py
from .processor import DataProcessor

# Importar o que existe no spline_interpolator.py
from .spline_interpolator import (
    InterpolationMethod,
    SplineInterpolator,
    SplineParameters,
)

# Listar o que está disponível quando alguém fizer "from loczcit_iqr.core import *"
__all__ = [
    # core basico
    'NOAADataLoader',
    'load_olr_data',
    'DataProcessor',
    'IQRDetector',
    'SplineInterpolator',
    'SplineParameters',
    'InterpolationMethod',
    # Climatologia
    'ClimatologiaZCIT',
    'calcular_climatologia_zcit_completa',
    'obter_climatologia_zcit_rapida',
    'comparar_com_climatologia_cientifica',
    'calcular_climatologia_personalizada',
    'salvar_climatologia',
    'carregar_climatologia',
    'executar_analise_limpa',
    'analise_zcit_rapida',
    # Regionais
    'climatologia_nordeste_brasileiro',
    'climatologia_amazonia_oriental',
    'climatologia_atlantico_tropical',
]
