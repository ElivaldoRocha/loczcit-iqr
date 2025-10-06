# examples/run_analysis.py
import argparse

import matplotlib.pyplot as plt

import loczcit_iqr as lz


def main(year: int, pentad: int, save_path: str = None):
    """
    Executa uma análise completa da ZCIT para um ano e pêntada específicos.
    """
    print(f"--- Iniciando análise para o ano {year}, pêntada {pentad} ---")

    # 1. Carregamento e Processamento
    loader = lz.NOAADataLoader()
    processor = lz.DataProcessor()

    print("Carregando dados OLR...")
    olr_data = loader.load_data(start_date=f"{year}-01-01", end_date=f"{year}-12-31")

    print("Criando pêntadas...")
    pentads_year = processor.create_pentads(olr_data=olr_data, year=year)

    # 2. Análise da Pêntada Alvo
    print(f"Analisando a pêntada {pentad}...")
    olr_pentada = pentads_year["olr"].sel(pentada=pentad)

    detector = lz.IQRDetector(constant=0.75)
    interpolator = lz.SplineInterpolator()

    min_coords = processor.find_minimum_coordinates(
        olr_pentada, method="column_minimum"
    )
    coords_valid, coords_outliers, _ = detector.detect_outliers(min_coords)
    zcit_line, _ = interpolator.interpolate(coords_valid)

    # 3. Visualização
    print("Gerando visualização...")
    start_date, end_date = lz.utils.pentada_to_dates(pentad, year)
    title = (
        f"Análise ZCIT - Pêntada {pentad} "
        f"({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m/%Y')})"
    )

    viz = lz.ZCITVisualizer(template="publication")
    fig, ax = viz.plot_complete_analysis(
        olr_data=olr_pentada,
        title=title,
        coords_valid=coords_valid,
        coords_outliers=coords_outliers,
        zcit_line=zcit_line,
        study_area_visible=True,
        save_path=save_path,
    )

    if save_path:
        print(f"Figura salva em: {save_path}")
    else:
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Executa uma análise da ZCIT com a biblioteca LOCZCIT-IQR."
    )
    parser.add_argument("year", type=int, help="Ano para análise (ex: 2022).")
    parser.add_argument("pentad", type=int, help="Pêntada para análise (1 a 73).")
    parser.add_argument(
        "--save",
        type=str,
        default=None,
        help="Caminho para salvar a imagem (ex: 'analise.png').",
    )

    args = parser.parse_args()

    main(args.year, args.pentad, args.save)
