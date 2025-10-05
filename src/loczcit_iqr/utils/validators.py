"""
loczcit_iqr/utils/validators.py
Funções de validação para a biblioteca LOCZCIT-IQR
"""

from datetime import datetime
from typing import Tuple, Union

import numpy as np


def validate_coordinates(
    coords: Tuple[float, float, float, float]
) -> Tuple[float, float, float, float]:
    """
    Valida coordenadas da área de estudo

    Parameters
    ----------
    coords : tuple
        Coordenadas (lat_min, lat_max, lon_min, lon_max)

    Returns
    -------
    tuple
        Coordenadas validadas

    Raises
    ------
    ValueError
        Se coordenadas forem inválidas
    """
    try:
        lat_min, lat_max, lon_min, lon_max = coords

        # Converter para float
        lat_min, lat_max = float(lat_min), float(lat_max)
        lon_min, lon_max = float(lon_min), float(lon_max)

        # Validar latitudes
        if not -90 <= lat_min <= 90:
            raise ValueError(
                f'lat_min inválida: {lat_min}. Deve estar entre -90 e 90'
            )
        if not -90 <= lat_max <= 90:
            raise ValueError(
                f'lat_max inválida: {lat_max}. Deve estar entre -90 e 90'
            )
        if lat_min >= lat_max:
            raise ValueError(
                f'lat_min ({lat_min}) deve ser menor que lat_max ({lat_max})'
            )

        # Validar longitudes
        if not -180 <= lon_min <= 180:
            raise ValueError(
                f'lon_min inválida: {lon_min}. Deve estar entre -180 e 180'
            )
        if not -180 <= lon_max <= 180:
            raise ValueError(
                f'lon_max inválida: {lon_max}. Deve estar entre -180 e 180'
            )
        if lon_min >= lon_max:
            raise ValueError(
                f'lon_min ({lon_min}) deve ser menor que lon_max ({lon_max})'
            )

        return (lat_min, lat_max, lon_min, lon_max)

    except (TypeError, ValueError) as e:
        raise ValueError(f'Coordenadas inválidas: {e}')


def validate_date(date: Union[str, datetime]) -> datetime:
    """
    Valida e converte data para datetime

    Parameters
    ----------
    date : str or datetime
        Data para validar

    Returns
    -------
    datetime
        Data validada

    Raises
    ------
    ValueError
        Se data for inválida
    """
    if isinstance(date, datetime):
        return date

    if isinstance(date, str):
        # Tentar diferentes formatos
        formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%d-%m-%Y',
            '%d/%m/%Y',
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date, fmt)
            except ValueError:
                continue

        # Se nenhum formato funcionou
        raise ValueError(
            f"Data '{date}' não está em formato reconhecido. "
            f"Use 'YYYY-MM-DD' ou datetime object"
        )

    raise TypeError(
        f'Data deve ser string ou datetime, recebido: {type(date)}'
    )


def validate_pentad_number(pentad: int) -> int:
    """
    Valida número de pentada

    Parameters
    ----------
    pentad : int
        Número da pentada

    Returns
    -------
    int
        Pentada validada

    Raises
    ------
    ValueError
        Se pentada for inválida
    """
    try:
        pentad = int(pentad)
    except (TypeError, ValueError):
        raise ValueError(
            f'Pentada deve ser um número inteiro, recebido: {pentad}'
        )

    if not 1 <= pentad <= 73:
        raise ValueError(
            f'Pentada deve estar entre 1 e 73, recebido: {pentad}'
        )

    return pentad


def validate_olr_values(
    olr_data: np.ndarray, valid_range: Tuple[float, float] = (50, 500)
) -> np.ndarray:
    """
    Valida valores de OLR

    Parameters
    ----------
    olr_data : numpy.ndarray
        Dados de OLR
    valid_range : tuple, optional
        Faixa válida de valores (min, max)

    Returns
    -------
    numpy.ndarray
        Dados validados (com NaN onde inválido)

    Notes
    -----
    Valores típicos de OLR variam entre 100 e 350 W/m²
    """
    min_val, max_val = valid_range

    # Criar máscara de valores válidos
    valid_mask = (olr_data >= min_val) & (olr_data <= max_val)

    # Aplicar máscara
    validated_data = np.where(valid_mask, olr_data, np.nan)

    # Avisar se muitos valores foram invalidados
    invalid_count = np.sum(~valid_mask)
    total_count = olr_data.size
    invalid_percentage = (invalid_count / total_count) * 100

    if invalid_percentage > 10:
        import warnings

        warnings.warn(
            f'{invalid_percentage:.1f}% dos valores OLR estão fora da faixa '
            f'válida {valid_range} W/m²'
        )

    return validated_data


def validate_iqr_constant(constant: float) -> float:
    """
    Valida constante IQR

    Parameters
    ----------
    constant : float
        Constante IQR

    Returns
    -------
    float
        Constante validada

    Raises
    ------
    ValueError
        Se constante for inválida
    """
    try:
        constant = float(constant)
    except (TypeError, ValueError):
        raise ValueError(
            f'Constante IQR deve ser numérica, recebido: {constant}'
        )

    if constant <= 0:
        raise ValueError(
            f'Constante IQR deve ser positiva, recebido: {constant}'
        )

    if constant < 0.5:
        import warnings

        warnings.warn(
            f'Constante IQR muito baixa ({constant}). '
            'Muitos pontos serão considerados outliers. '
            'Valores típicos: 0.75 (restritivo), 1.5 (padrão), 3.0 (permissivo)'
        )
    elif constant > 3.0:
        import warnings

        warnings.warn(
            f'Constante IQR muito alta ({constant}). '
            'Poucos outliers serão detectados. '
            'Valores típicos: 0.75 (restritivo), 1.5 (padrão), 3.0 (permissivo)'
        )

    return constant
