# Em loczcit_iqr/plotting/style.py

from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt


def setup_loczcit_style():
    """
    [VERSÃO COMPLETA]
    Configura um estilo visual profissional e consistente para os gráficos da
    biblioteca loczcit_iqr, estabelecendo uma hierarquia tipográfica com a
    fonte Roboto Serif.
    """
    try:
        # O arquivo style.py está agora em loczcit_iqr/plotting/style.py
        # As fontes estão em assets/fonts/static/ (dois níveis acima)
        font_dir_path = (
            Path(__file__).parent.parent.parent / 'assets' / 'fonts' / 'static'
        )
        #                                      ^^^^^^^ ^^^^^^^ - Subimos dois níveis

        if not font_dir_path.is_dir():
            print(f'⚠️ Diretório de fontes não encontrado: {font_dir_path}')
            # Tentativa alternativa para desenvolvimento
            alt_path = Path(__file__).parent / 'assets' / 'fonts' / 'static'
            if alt_path.is_dir():
                font_dir_path = alt_path
                print(f'✅ Usando caminho alternativo: {font_dir_path}')
            else:
                return

        font_files = fm.findSystemFonts(fontpaths=[str(font_dir_path)])
        if not font_files:
            print(
                f'⚠️ Nenhum arquivo de fonte .ttf encontrado em: {font_dir_path}'
            )
            return

        for font_file in font_files:
            fm.fontManager.addfont(font_file)

        print(
            f'✅ {len(font_files)} fontes da biblioteca loczcit_iqr registradas com sucesso.'
        )

        # --- ETAPA 4: Definir a Hierarquia Tipográfica Padrão ---

        # Define a família de fontes padrão
        plt.rcParams['font.family'] = 'serif'
        plt.rcParams['font.serif'] = [
            'Roboto Serif',
            'DejaVu Serif',
        ]   # Fallback

        # Título principal do gráfico (ax.set_title)
        plt.rcParams['axes.titlesize'] = 16
        plt.rcParams[
            'axes.titleweight'
        ] = 'bold'  # 'bold' -> RobotoSerif-Bold.ttf

        # Título da figura inteira (fig.suptitle)
        plt.rcParams['figure.titlesize'] = 20
        plt.rcParams[
            'figure.titleweight'
        ] = 'black'   # 'black' -> RobotoSerif-Black.ttf

        # Rótulos dos eixos (ax.set_xlabel, ax.set_ylabel)
        plt.rcParams['axes.labelsize'] = 12
        plt.rcParams[
            'axes.labelweight'
        ] = 'regular'   # 'regular' -> RobotoSerif-Regular.ttf

        # Rótulos dos "ticks" (os números nos eixos)
        plt.rcParams['xtick.labelsize'] = 10
        plt.rcParams['ytick.labelsize'] = 10

        # Legenda
        plt.rcParams['legend.fontsize'] = 10
        # Você também pode controlar o título da legenda:
        # plt.rcParams['legend.title_fontsize'] = 11

        # Outras configurações úteis
        plt.rcParams[
            'axes.unicode_minus'
        ] = False   # Para exibir o sinal de menos corretamente
        plt.rcParams[
            'figure.dpi'
        ] = 100   # Aumenta a resolução padrão das figuras
        plt.rcParams['savefig.dpi'] = 300   # Alta resolução ao salvar
        plt.rcParams[
            'savefig.bbox'
        ] = 'tight'   # Remove excesso de borda branca

        print('🎨 Estilo tipográfico profissional loczcit_iqr aplicado.')

    except Exception as e:
        print(f'⚠️ Erro ao configurar o estilo loczcit_iqr: {e}')
        print('Gráficos serão gerados com o estilo padrão do Matplotlib.')


# ls loczcit-library\assets\fonts\static
# Name:
# RobotoSerif-Thin.ttf
# RobotoSerif-ExtraLight.ttf
# RobotoSerif-Regular.ttf
# RobotoSerif-Light.ttf
# RobotoSerif-Medium.ttf
# RobotoSerif-SemiBold.ttf
# RobotoSerif-Bold.ttf
# RobotoSerif-ExtraBold.ttf
# RobotoSerif-Black.ttf
# RobotoSerif-ThinItalic.ttf
# RobotoSerif-ExtraLightItalic.ttf
# RobotoSerif-LightItalic.ttf
# RobotoSerif-Italic.ttf
# RobotoSerif-MediumItalic.ttf
# RobotoSerif-SemiBoldItalic.ttf
# RobotoSerif-BoldItalic.ttf
# RobotoSerif-ExtraBoldItalic.ttf
# RobotoSerif-BlackItalic.ttf
