"""
Core functionality for loczcit_iqr.

This module provides the core data loading, processing, and analysis tools
for ITCZ (Intertropical Convergence Zone) research using OLR data.

Modules
-------
data_loader : NOAA OLR data downloading and loading
data_loader_era5 : ERA5 Reanalysis data (alternative to NOAA)
processor : Data processing and pentad creation
iqr_detector : Outlier detection using IQR method
spline_interpolator : Spline interpolation for ITCZ line
climatologia : ITCZ climatology analysis
"""

# =============================================================================
# DATA LOADERS
# =============================================================================

# NOAA Data Loader (primary source)
# =============================================================================
# CLIMATOLOGY
# =============================================================================
from .climatologia import (
    # Classes
    ClimatologiaZCIT,
    analise_zcit_rapida,
    calcular_climatologia_personalizada,
    # Funções principais
    calcular_climatologia_zcit_completa,
    carregar_climatologia,
    climatologia_amazonia_oriental,
    climatologia_atlantico_tropical,
    # Climatologias regionais
    climatologia_nordeste_brasileiro,
    comparar_com_climatologia_cientifica,
    # Análise
    executar_analise_limpa,
    obter_climatologia_zcit_rapida,
    # I/O
    salvar_climatologia,
)
from .data_loader import (
    NOAADataLoader,
    load_olr_data,
)

# ERA5 Data Loader (alternative source when NOAA is unavailable)
from .data_loader_era5 import (
    ERA5DataLoader,
    load_era5_olr,
)

# =============================================================================
# ITCZ DETECTION
# =============================================================================
from .iqr_detector import IQRDetector

# =============================================================================
# DATA PROCESSING
# =============================================================================
from .processor import DataProcessor

# =============================================================================
# INTERPOLATION
# =============================================================================
from .spline_interpolator import (
    InterpolationMethod,
    SplineInterpolator,
    SplineParameters,
)

# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # -------------------------------------------------------------------------
    # DATA LOADERS
    # -------------------------------------------------------------------------
    "NOAADataLoader",  # NOAA OLR data loader
    "load_olr_data",  # Quick function for NOAA data
    "ERA5DataLoader",  # ERA5 Reanalysis data loader
    "load_era5_olr",  # Quick function for ERA5 data
    # -------------------------------------------------------------------------
    # PROCESSING
    # -------------------------------------------------------------------------
    "DataProcessor",  # Core data processing
    # -------------------------------------------------------------------------
    # DETECTION
    # -------------------------------------------------------------------------
    "IQRDetector",  # Outlier detection
    # -------------------------------------------------------------------------
    # INTERPOLATION
    # -------------------------------------------------------------------------
    "SplineInterpolator",  # Spline interpolation
    "SplineParameters",  # Interpolation parameters
    "InterpolationMethod",  # Interpolation methods enum
    # -------------------------------------------------------------------------
    # CLIMATOLOGY - Main
    # -------------------------------------------------------------------------
    "ClimatologiaZCIT",  # Main climatology class
    "calcular_climatologia_zcit_completa",  # Complete climatology
    "obter_climatologia_zcit_rapida",  # Quick climatology
    "comparar_com_climatologia_cientifica",  # Compare with literature
    "calcular_climatologia_personalizada",  # Custom climatology
    # -------------------------------------------------------------------------
    # CLIMATOLOGY - I/O
    # -------------------------------------------------------------------------
    "salvar_climatologia",  # Save climatology
    "carregar_climatologia",  # Load climatology
    # -------------------------------------------------------------------------
    # CLIMATOLOGY - Analysis
    # -------------------------------------------------------------------------
    "executar_analise_limpa",  # Clean analysis
    "analise_zcit_rapida",  # Quick ITCZ analysis
    # -------------------------------------------------------------------------
    # CLIMATOLOGY - Regional
    # -------------------------------------------------------------------------
    "climatologia_nordeste_brasileiro",  # Brazilian Northeast
    "climatologia_amazonia_oriental",  # Eastern Amazon
    "climatologia_atlantico_tropical",  # Tropical Atlantic
]

# =============================================================================
# VERSION INFO
# =============================================================================

__version__ = "1.0.0"
__author__ = "LOCZCIT-IQR Development Team"

# =============================================================================
# MODULE METADATA
# =============================================================================

_CORE_MODULES = {
    "data_loader": "NOAA OLR data loading",
    "data_loader_era5": "ERA5 Reanalysis data loading (alternative)",
    "processor": "Data processing and pentad creation",
    "iqr_detector": "Outlier detection using IQR",
    "spline_interpolator": "Spline interpolation",
    "climatologia": "ITCZ climatology analysis",
}


def get_available_loaders():
    """
    Return information about available data loaders.

    Returns
    -------
    dict
        Dictionary with loader names and descriptions

    Examples
    --------
    >>> from loczcit_iqr.core import get_available_loaders
    >>> loaders = get_available_loaders()
    >>> print(loaders)
    """
    return {
        "NOAADataLoader": {
            "description": "NOAA OLR CDR data (primary source)",
            "status": "operational",
            "temporal_coverage": "1979-present",
            "spatial_resolution": "1° × 1°",
            "source": "NOAA NCEI",
        },
        "ERA5DataLoader": {
            "description": "ERA5 Reanalysis OLR data (alternative)",
            "status": "operational",
            "temporal_coverage": "1940-present",
            "spatial_resolution": "0.25° × 0.25°",
            "source": "ECMWF Copernicus CDS",
        },
    }


def check_core_modules():
    """
    Check status of all core modules.

    Returns
    -------
    dict
        Status of each module

    Examples
    --------
    >>> from loczcit_iqr.core import check_core_modules
    >>> status = check_core_modules()
    >>> print(status)
    """
    import sys

    status = {}

    for module_name, description in _CORE_MODULES.items():
        try:
            __import__(f"loczcit_iqr.core.{module_name}")
            status[module_name] = {"available": True, "description": description}
        except ImportError as e:
            status[module_name] = {
                "available": False,
                "description": description,
                "error": str(e),
            }

    return status


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def quick_load(start_date, end_date=None, source="auto", **kwargs):
    """
    Quick data loading with automatic source selection.

    Parameters
    ----------
    start_date : str
        Start date (format: 'YYYY-MM-DD')
    end_date : str, optional
        End date (if None, uses end of month)
    source : str, optional
        Data source: 'noaa', 'era5', or 'auto' (default)
        If 'auto', tries NOAA first, falls back to ERA5
    **kwargs
        Additional arguments for the loader

    Returns
    -------
    xarray.Dataset
        OLR data

    Examples
    --------
    >>> from loczcit_iqr.core import quick_load
    >>>
    >>> # Auto-select source
    >>> data = quick_load("2025-01-01", "2025-01-31")
    >>>
    >>> # Force ERA5
    >>> data = quick_load("2025-01-01", source='era5')
    """
    import warnings

    if source == "auto":
        # Try NOAA first
        try:
            loader = NOAADataLoader()
            return loader.load_data(start_date, end_date, **kwargs)
        except Exception as e:
            warnings.warn(f"NOAA loader failed ({e}), trying ERA5...", UserWarning)
            # Fall back to ERA5
            loader = ERA5DataLoader()
            return loader.load_data(start_date, end_date, **kwargs)

    elif source.lower() == "noaa":
        loader = NOAADataLoader()
        return loader.load_data(start_date, end_date, **kwargs)

    elif source.lower() == "era5":
        loader = ERA5DataLoader()
        return loader.load_data(start_date, end_date, **kwargs)

    else:
        raise ValueError(
            f"Unknown source: {source}. Valid options: 'noaa', 'era5', 'auto'"
        )


# =============================================================================
# CONVENIENCE IMPORTS FOR BACKWARDS COMPATIBILITY
# =============================================================================

# Allow users to still do: from loczcit_iqr.core import *
# This maintains backwards compatibility with existing code

__all__.extend(
    [
        "check_core_modules",
        "get_available_loaders",
        "quick_load",
    ]
)
