"""
loczcit_iqr - Biblioteca para detecção de outliers em dados diários de Radiação de Onda Longa.

Esta biblioteca fornece ferramentas completas para análise da Zona de Convergência
Intertropical (ZCIT) usando metodologia IQR (Interquartile Range) para detecção
de outliers em dados de OLR (Outgoing Longwave Radiation).

ANALOGIA DA BIBLIOTECA 📚
Como uma biblioteca especializada em meteorologia tropical que oferece:
- 🔍 Lupas especializadas (IQRDetector) para encontrar dados anômalos
- 📊 Processadores de dados (DataProcessor) para organizar informações climáticas
- 🌐 Carregadores (NOAADataLoader, ERA5DataLoader) para buscar dados de fontes diversas # MODIFICADO
- 📈 Interpoladores (SplineInterpolator) para criar linhas suaves
- 🎨 Visualizadores (ZCITVisualizer) para criar mapas e gráficos profissionais
- 📋 Climatologias (ClimatologiaZCIT) para comparação com padrões históricos

Modules:
    core: Funcionalidades principais de processamento e análise
    plotting: Visualização e criação de gráficos profissionais
    utils: Utilidades auxiliares (pentadas, validadores)

Examples:
    Análise rápida da ZCIT:
    >>> import loczcit_iqr as lz
    >>> loader = lz.NOAADataLoader()
    >>> data = loader.load_data('2024-03-01', '2024-03-31')
    >>> processor = lz.DataProcessor()
    >>> coords = processor.find_minimum_coordinates(data['olr'])
    >>> detector = lz.IQRDetector()
    >>> valid, outliers, stats = detector.detect_outliers(coords)

    Visualização completa:
    >>> viz = lz.ZCITVisualizer(template='publication')
    >>> fig, ax = viz.quick_plot(data, pentada=30, zcit_coords=valid)

    Análise climatológica:
    >>> status, desvio, interpretacao = lz.analise_zcit_rapida(-0.5, 3)
    >>> print(f"ZCIT está: {status}")

Author: LOCZCIT-IQR Development Team
License: MIT
Version: 0.1.0
"""

# Versão da biblioteca
__version__ = "0.0.1"

# Informações sobre a biblioteca
__author__ = "Elivaldo Rocha developer of LOCZCIT-IQR"
__email__ = "carvalhovaldo09@gmail.com"
__license__ = "MIT"
__description__ = "Biblioteca para análise da ZCIT usando metodologia IQR"

# ============================================================================
# IMPORTAÇÕES CORE (Essenciais)
# ============================================================================

# Data Loading (NOAA)
try:
    from loczcit_iqr.core.data_loader import (
        NOAADataLoader,
        carregar_olr_robusto,
        diagnosticar_arquivo_netcdf,
        load_olr_data,
    )

    _has_data_loader = True
except ImportError as e:
    _has_data_loader = False
    _data_loader_error = str(e)

# Data Loading (ERA5) # NOVO - Bloco para o loader ERA5
try:
    from loczcit_iqr.core.data_loader_era5 import (
        ERA5DataLoader,
        load_era5_olr,
    )

    _has_data_loader_era5 = True
except ImportError as e:
    _has_data_loader_era5 = False
    _data_loader_era5_error = str(e)


# Data Processing
try:
    from loczcit_iqr.core.processor import DataProcessor

    _has_processor = True
except ImportError as e:
    _has_processor = False
    _processor_error = str(e)

# IQR Detection
try:
    from loczcit_iqr.core.iqr_detector import IQRDetector

    _has_iqr = True
except ImportError as e:
    _has_iqr = False
    _iqr_error = str(e)

# Spline Interpolation
try:
    from loczcit_iqr.core.spline_interpolator import (
        InterpolationMethod,
        SplineInterpolator,
        SplineParameters,
    )

    _has_spline = True
except ImportError as e:
    _has_spline = False
    _spline_error = str(e)

# Climatologia (Módulo mais complexo)
try:
    from loczcit_iqr.core.climatologia import (  # Funções regionais; Funções temporais; Análise e comparação; Verificações mensais específicas
        ClimatologiaZCIT,
        analisar_climatologia_temporal,
        analise_zcit_rapida,
        calcular_climatologia_personalizada,
        calcular_climatologia_zcit_completa,
        carregar_climatologia,
        climatologia_amazonia_oriental,
        climatologia_atlantico_tropical,
        climatologia_nordeste_brasileiro,
        comparar_climatologias_temporais,
        comparar_com_climatologia_cientifica,
        criar_climatologia_diaria_detalhada,
        criar_climatologia_mensal_rapida,
        criar_climatologia_olr,
        criar_climatologia_pentadas_operacional,
        criar_climatologia_rapida,
        executar_analise_limpa,
        executar_climatologias_completas_zcit,
        obter_climatologia_zcit_1994_2023_NOAA,
        obter_climatologia_zcit_rapida,
        salvar_climatologia,
        validar_climatologia,
        verificar_zcit_abril,
        verificar_zcit_agosto,
        verificar_zcit_dezembro,
        verificar_zcit_fevereiro,
        verificar_zcit_janeiro,
        verificar_zcit_julho,
        verificar_zcit_junho,
        verificar_zcit_maio,
        verificar_zcit_marco,
        verificar_zcit_novembro,
        verificar_zcit_outubro,
        verificar_zcit_setembro,
        visualizar_climatologia,
    )

    _has_climatologia = True
except ImportError as e:
    _has_climatologia = False
    _climatologia_error = str(e)

# ============================================================================
# IMPORTAÇÕES PLOTTING (Visualização)
# ============================================================================

try:
    from loczcit_iqr.plotting.visualizer import (
        TEMPLATES,
        ZCITColormap,
        ZCITPlotter,
        ZCITVisualizer,
        check_plotting_dependencies,
        create_publication_figure,
        plot_complete_zcit_analysis,
        plot_zcit_quick,
        plot_zcit_quick_analysis,
    )

    _has_plotting = True
except ImportError as e:
    _has_plotting = False
    _plotting_error = str(e)

try:
    from loczcit_iqr.plotting.style import setup_loczcit_style

    _has_style = True
except ImportError as e:
    _has_style = False
    _style_error = str(e)

# ============================================================================
# IMPORTAÇÕES UTILS (Utilidades)
# ============================================================================

try:
    from loczcit_iqr.utils.pentadas import (
        PENTADA_DICT,
        date_to_pentada,
        generate_pentada_dict,
        list_pentadas,
        pentada_label,
        pentada_to_dates,
    )

    _has_pentadas = True
except ImportError as e:
    _has_pentadas = False
    _pentadas_error = str(e)

try:
    from loczcit_iqr.utils.validators import (
        validate_coordinates,
        validate_date,
        validate_iqr_constant,
        validate_olr_values,
        validate_pentad_number,
    )

    _has_validators = True
except ImportError as e:
    _has_validators = False
    _validators_error = str(e)

# ============================================================================
# LISTA DE EXPORTAÇÃO (__all__)
# ============================================================================

__all__ = [
    # Metadados
    "__version__",
    "__author__",
    "__license__",
    # Funções de conveniência
    "check_modules",
    "get_version_info",
    "quick_start_guide",
]

# Adicionar exports condicionais baseados na disponibilidade dos módulos

# Core exports
if _has_data_loader:
    __all__.extend(
        [
            "NOAADataLoader",
            "carregar_olr_robusto",
            "diagnosticar_arquivo_netcdf",
            "load_olr_data",
        ]
    )

if _has_data_loader_era5:  # NOVO - Exporta os objetos do ERA5
    __all__.extend(
        [
            "ERA5DataLoader",
            "load_era5_olr",
        ]
    )

if _has_processor:
    __all__.append("DataProcessor")

if _has_iqr:
    __all__.append("IQRDetector")

if _has_spline:
    __all__.extend(
        [
            "InterpolationMethod",
            "SplineInterpolator",
            "SplineParameters",
        ]
    )

if _has_climatologia:
    __all__.extend(
        [
            # Classe principal
            "ClimatologiaZCIT",
            # Funções rápidas
            "obter_climatologia_zcit_rapida",
            "obter_climatologia_zcit_1994_2023_NOAA",
            "analise_zcit_rapida",
            "executar_analise_limpa",
            # Funções de análise
            "comparar_com_climatologia_cientifica",
            "calcular_climatologia_zcit_completa",
            "calcular_climatologia_personalizada",
            # Manipulação de arquivos
            "salvar_climatologia",
            "carregar_climatologia",
            # Criação de climatologias
            "criar_climatologia_olr",
            "validar_climatologia",
            "visualizar_climatologia",
            "criar_climatologia_rapida",
            # Funções regionais
            "climatologia_nordeste_brasileiro",
            "climatologia_amazonia_oriental",
            "climatologia_atlantico_tropical",
            # Funções temporais
            "executar_climatologias_completas_zcit",
            "criar_climatologia_mensal_rapida",
            "criar_climatologia_diaria_detalhada",
            "criar_climatologia_pentadas_operacional",
            # Análise
            "analisar_climatologia_temporal",
            "comparar_climatologias_temporais",
            # Verificações mensais
            "verificar_zcit_janeiro",
            "verificar_zcit_fevereiro",
            "verificar_zcit_marco",
            "verificar_zcit_abril",
            "verificar_zcit_maio",
            "verificar_zcit_junho",
            "verificar_zcit_julho",
            "verificar_zcit_agosto",
            "verificar_zcit_setembro",
            "verificar_zcit_outubro",
            "verificar_zcit_novembro",
            "verificar_zcit_dezembro",
        ]
    )

# Plotting exports
if _has_plotting:
    __all__.extend(
        [
            "TEMPLATES",
            "ZCITColormap",
            "ZCITPlotter",
            "ZCITVisualizer",
            "check_plotting_dependencies",
            "create_publication_figure",
            "plot_complete_zcit_analysis",
            "plot_zcit_quick",
            "plot_zcit_quick_analysis",
        ]
    )

if _has_style:
    __all__.append("setup_loczcit_style")

# Utils exports
if _has_pentadas:
    __all__.extend(
        [
            "PENTADA_DICT",
            "date_to_pentada",
            "generate_pentada_dict",
            "list_pentadas",
            "pentada_label",
            "pentada_to_dates",
        ]
    )

if _has_validators:
    __all__.extend(
        [
            "validate_coordinates",
            "validate_date",
            "validate_iqr_constant",
            "validate_olr_values",
            "validate_pentad_number",
        ]
    )


# ============================================================================
# FUNÇÕES DE CONVENIÊNCIA E DIAGNÓSTICO
# ============================================================================


def check_modules(verbose: bool = True) -> dict:
    """
    Verifica quais módulos estão disponíveis na biblioteca loczcit_iqr.

    ANALOGIA DO MÉDICO DIAGNÓSTICO 🏥
    Como um médico que verifica quais "órgãos" (módulos) da biblioteca
    estão funcionando corretamente e quais precisam de atenção.

    Parameters
    ----------
    verbose : bool, default True
        Se True, imprime relatório detalhado no console

    Returns
    -------
    dict
        Status detalhado de cada módulo

    Example
    -------
    >>> import loczcit_iqr as lz
    >>> status = lz.check_modules()
    >>> if status['core']['all_available']:
    ...     print("✅ Todos os módulos core estão disponíveis!")
    """
    # MODIFICADO - Adicionado 'data_loader_era5' ao dicionário de status
    modules_status = {
        "core": {
            "data_loader (NOAA)": _has_data_loader,
            "data_loader_era5 (ERA5)": _has_data_loader_era5,
            "processor": _has_processor,
            "iqr_detector": _has_iqr,
            "spline_interpolator": _has_spline,
            "climatologia": _has_climatologia,
            "all_available": all(
                [
                    _has_data_loader,
                    _has_data_loader_era5,
                    _has_processor,
                    _has_iqr,
                    _has_spline,
                    _has_climatologia,
                ]
            ),
        },
        "plotting": {
            "visualizer": _has_plotting,
            "style": _has_style,
            "all_available": all([_has_plotting, _has_style]),
        },
        "utils": {
            "pentadas": _has_pentadas,
            "validators": _has_validators,
            "all_available": all([_has_pentadas, _has_validators]),
        },
    }

    if verbose:
        print("🌊 LOCZCIT-IQR - Status dos Módulos")
        print("=" * 50)

        for category, modules in modules_status.items():
            print(f"\n📦 {category.upper()}:")

            for module_name, available in modules.items():
                if module_name == "all_available":
                    continue

                icon = "✅" if available else "❌"
                print(f"   {icon} {module_name}")

                # Mostrar erro específico se disponível
                if not available:
                    # MODIFICADO - Lógica para pegar nome correto do módulo
                    error_var_name = module_name.split(" ")[
                        0
                    ]  # Pega 'data_loader' de 'data_loader (NOAA)'
                    error_var = f"_{error_var_name}_error"
                    if error_var in globals():
                        error_msg = globals()[error_var]
                        print(f"       💡 Erro: {error_msg}")

            # Status geral da categoria
            all_ok = modules["all_available"]
            status_icon = "✅" if all_ok else "⚠️"
            status_text = "Completo" if all_ok else "Parcial"
            print(f"   {status_icon} Status {category}: {status_text}")

        # Recomendações
        print("\n💡 RECOMENDAÇÕES:")

        missing_modules = []
        for category, modules in modules_status.items():
            if not modules["all_available"]:
                missing_modules.append(category)

        if missing_modules:
            print(f"   ⚠️  Módulos com problemas: {', '.join(missing_modules)}")
            print("   🔧 Verifique dependências com: pip install -e .")
            if not _has_data_loader_era5:
                print("   🔧 Para usar ERA5, instale: pip install cdsapi")
        else:
            print("   🎉 Todos os módulos estão funcionando perfeitamente!")

        # Guia rápido
        print("\n📚 Para começar, use: lz.quick_start_guide()")

    return modules_status


def get_version_info() -> dict:
    """
    Retorna informações detalhadas sobre a versão da biblioteca.

    Returns
    -------
    dict
        Informações da versão, dependências e build
    """
    import platform
    import sys

    # Verificar dependências principais
    dependencies = {}

    try:
        import numpy as np

        dependencies["numpy"] = np.__version__
    except ImportError:
        dependencies["numpy"] = "Não instalado"

    try:
        import xarray as xr

        dependencies["xarray"] = xr.__version__
    except ImportError:
        dependencies["xarray"] = "Não instalado"

    try:
        import matplotlib

        dependencies["matplotlib"] = matplotlib.__version__
    except ImportError:
        dependencies["matplotlib"] = "Não instalado"

    try:
        import cartopy

        dependencies["cartopy"] = cartopy.__version__
    except ImportError:
        dependencies["cartopy"] = "Não instalado"

    try:
        import geopandas as gpd

        dependencies["geopandas"] = gpd.__version__
    except ImportError:
        dependencies["geopandas"] = "Não instalado"

    # NOVO - Adicionado verificação do cdsapi
    try:
        import cdsapi

        dependencies["cdsapi"] = "Instalado"
    except ImportError:
        dependencies["cdsapi"] = "Não instalado"

    return {
        "loczcit_iqr_version": __version__,
        "python_version": sys.version,
        "platform": platform.platform(),
        "dependencies": dependencies,
        "modules_available": check_modules(verbose=False),
        "build_info": {
            "author": __author__,
            "license": __license__,
            "description": __description__,
        },
    }


def quick_start_guide() -> None:
    """
    Exibe um guia rápido de uso da biblioteca.

    ANALOGIA DO GUIA TURÍSTICO 🗺️
    Como um guia experiente que mostra os principais pontos turísticos
    (funcionalidades) da biblioteca de forma organizada e didática.
    """
    # MODIFICADO - Adicionado exemplo do ERA5DataLoader
    print("🌊 LOCZCIT-IQR - Guia Rápido de Uso")
    print("=" * 60)
    print("📚 Biblioteca para análise da ZCIT com detecção IQR de outliers")

    print("\n🚀 ANÁLISE RÁPIDA (3 passos):")
    print("   1️⃣  import loczcit_iqr as lz")
    print("   2️⃣  coords = lz.DataProcessor().find_minimum_coordinates(data)")
    print("   3️⃣  status = lz.analise_zcit_rapida(-0.5, 3)  # lat, mês")

    print("\n📊 CARREGAMENTO DE DADOS (NOAA - Padrão):")
    print("   loader = lz.NOAADataLoader()")
    print("   data = loader.load_data('2024-03-01', '2024-03-31')")
    print("   # Busca automática + download + processamento")

    print("\n🛰️ CARREGAMENTO DE DADOS (ERA5 - Alternativa):")
    print("   # Requer credenciais do Copernicus/ECMWF")
    print("   loader_era5 = lz.ERA5DataLoader()")
    print("   # Na primeira vez, configure:")
    print("   # loader_era5.setup_credentials(key='UID:API_KEY')")
    print("   data_era5 = loader_era5.load_data('2025-09-01', '2025-09-05')")

    print("\n🔍 DETECÇÃO DE OUTLIERS:")
    print("   detector = lz.IQRDetector(constant=1.5)")
    print("   validos, outliers, stats = detector.detect_outliers(coords)")
    print("   # Método IQR científico para dados climáticos")

    print("\n📈 INTERPOLAÇÃO E LINHAS:")
    print("   interpolator = lz.SplineInterpolator()")
    print("   linha_zcit, estatisticas = interpolator.interpolate(coords)")
    print("   # Cria linhas suaves da ZCIT")

    print("\n🎨 VISUALIZAÇÃO PROFISSIONAL:")
    print("   viz = lz.ZCITVisualizer(template='publication')")
    print("   fig, ax = viz.quick_plot(data, pentada=30)")
    print("   # Mapas prontos para artigos científicos")

    print("\n🌡️ ANÁLISE CLIMATOLÓGICA:")
    print("   # Comparação com padrões históricos")
    print("   status, desvio, interpretacao = lz.comparar_com_climatologia_cientifica(")
    print("       mes=3, posicao_encontrada=-0.5")
    print("   )")

    print("\n📋 CLIMATOLOGIAS PERSONALIZADAS:")
    print("   # Para regiões específicas")
    print("   clima_ne = lz.climatologia_nordeste_brasileiro()")
    print("   clima_amazonia = lz.climatologia_amazonia_oriental()")

    print("\n🔧 VERIFICAÇÃO DO SISTEMA:")
    print("   lz.check_modules()  # Verifica módulos instalados")
    print("   lz.get_version_info()  # Informações da versão")

    print("\n💡 DICAS IMPORTANTES:")
    print("   • Use templates: 'publication', 'presentation', 'web', 'report'")
    print("   • Constantes IQR: 0.75 (restritivo), 1.5 (padrão), 3.0 (permissivo)")
    print("   • Pentadas: períodos de 5 dias (1-73 por ano)")
    print("   • Study areas: BBOX, arquivos .shp/.geojson, ou GeoDataFrames")

    print("\n📖 DOCUMENTAÇÃO COMPLETA:")
    print("   https://loczcit-iqr.readthedocs.io")

    print("\n🎯 EXEMPLO COMPLETO:")
    print("   ```python")
    print("   import loczcit_iqr as lz")
    print("   ")
    print("   # Carregar dados")
    print("   loader = lz.NOAADataLoader()")
    print("   data = loader.load_data('2024-03-01', '2024-03-05')")
    print("   ")
    print("   # Processar e detectar ZCIT")
    print("   processor = lz.DataProcessor()")
    print("   coords = processor.find_minimum_coordinates(data['olr'])")
    print("   ")
    print("   # Detectar outliers")
    print("   detector = lz.IQRDetector()")
    print("   validos, outliers, stats = detector.detect_outliers(coords)")
    print("   ")
    print("   # Visualizar")
    print("   viz = lz.ZCITVisualizer(template='publication')")
    print("   fig, ax = viz.quick_plot(data, pentada=30, zcit_coords=validos)")
    print("   ```")

    # Verificar se módulos estão disponíveis
    module_status = check_modules(verbose=False)

    missing_core = not module_status["core"]["all_available"]
    missing_plotting = not module_status["plotting"]["all_available"]

    if missing_core or missing_plotting:
        print("\n⚠️  AVISO:")
        if missing_core:
            print("   ❌ Alguns módulos CORE não estão disponíveis")
        if missing_plotting:
            print("   ❌ Módulos de PLOTTING não estão disponíveis")
        print("   🔧 Execute: pip install -e . para instalar dependências")
    else:
        print("\n✅ Todos os módulos estão disponíveis! Boa análise! 🌊")


# ============================================================================
# INICIALIZAÇÃO E CONFIGURAÇÃO AUTOMÁTICA
# ============================================================================


def _initialize_library():
    """
    Inicialização automática da biblioteca.

    Executa configurações necessárias quando a biblioteca é importada.
    """
    # Configurar estilo de plotting se disponível
    if _has_style:
        try:
            setup_loczcit_style()
        except Exception:
            # Silenciosamente falha se não conseguir configurar estilo
            pass

    # Configurar avisos
    import warnings

    # Suprimir avisos específicos que são normais na biblioteca
    warnings.filterwarnings("ignore", category=UserWarning, module="cartopy")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="matplotlib")


# Executar inicialização
_initialize_library()

# ============================================================================
# MENSAGEM DE BOAS-VINDAS (apenas se importado interativamente)
# ============================================================================


def _show_welcome_message():
    """Mostra mensagem de boas-vindas se importado interativamente."""
    import sys

    # Só mostra se estiver em ambiente interativo
    if hasattr(sys, "ps1") or hasattr(sys, "ps2"):
        print(f"🌊 LOCZCIT-IQR v{__version__} carregada!")
        print("   📖 Use lz.quick_start_guide() para começar")
        print("   🔧 Use lz.check_modules() para verificar módulos")


# Mostrar boas-vindas em ambiente interativo
try:
    _show_welcome_message()
except Exception:
    # Falha silenciosamente se houver qualquer problema
    pass
