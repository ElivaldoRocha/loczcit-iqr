"""
loczcit_iqr/utils/pentadas.py
Utilidades para conversão e manipulação de pentadas (WMO Standard)
"""

from datetime import datetime, timedelta

# Dicionário padrão das 73 pentadas para anos NÃO bissextos
PENTADA_DICT = {
    "1° Pentada": ("01-jan", "05-jan", "01–05/jan"),
    "2° Pentada": ("06-jan", "10-jan", "06–10/jan"),
    "3° Pentada": ("11-jan", "15-jan", "11–15/jan"),
    "4° Pentada": ("16-jan", "20-jan", "16–20/jan"),
    "5° Pentada": ("21-jan", "25-jan", "21–25/jan"),
    "6° Pentada": ("26-jan", "30-jan", "26–30/jan"),
    "7° Pentada": ("31-jan", "04-fev", "31/jan–04/fev"),
    "8° Pentada": ("05-fev", "09-fev", "05–09/fev"),
    "9° Pentada": ("10-fev", "14-fev", "10–14/fev"),
    "10° Pentada": ("15-fev", "19-fev", "15–19/fev"),
    "11° Pentada": ("20-fev", "24-fev", "20–24/fev"),
    "12° Pentada": ("25-fev", "01-mar", "25/fev–01/mar"),
    "13° Pentada": ("02-mar", "06-mar", "02–06/mar"),
    "14° Pentada": ("07-mar", "11-mar", "07–11/mar"),
    "15° Pentada": ("12-mar", "16-mar", "12–16/mar"),
    "16° Pentada": ("17-mar", "21-mar", "17–21/mar"),
    "17° Pentada": ("22-mar", "26-mar", "22–26/mar"),
    "18° Pentada": ("27-mar", "31-mar", "27–31/mar"),
    "19° Pentada": ("01-abr", "05-abr", "01–05/abr"),
    "20° Pentada": ("06-abr", "10-abr", "06–10/abr"),
    "21° Pentada": ("11-abr", "15-abr", "11–15/abr"),
    "22° Pentada": ("16-abr", "20-abr", "16–20/abr"),
    "23° Pentada": ("21-abr", "25-abr", "21–25/abr"),
    "24° Pentada": ("26-abr", "30-abr", "26–30/abr"),
    "25° Pentada": ("01-mai", "05-mai", "01–05/mai"),
    "26° Pentada": ("06-mai", "10-mai", "06–10/mai"),
    "27° Pentada": ("11-mai", "15-mai", "11–15/mai"),
    "28° Pentada": ("16-mai", "20-mai", "16–20/mai"),
    "29° Pentada": ("21-mai", "25-mai", "21–25/mai"),
    "30° Pentada": ("26-mai", "30-mai", "26–30/mai"),
    "31° Pentada": ("31-mai", "04-jun", "31/mai–04/jun"),
    "32° Pentada": ("05-jun", "09-jun", "05–09/jun"),
    "33° Pentada": ("10-jun", "14-jun", "10–14/jun"),
    "34° Pentada": ("15-jun", "19-jun", "15–19/jun"),
    "35° Pentada": ("20-jun", "24-jun", "20–24/jun"),
    "36° Pentada": ("25-jun", "29-jun", "25–29/jun"),
    "37° Pentada": ("30-jun", "04-jul", "30/jun–04/jul"),
    "38° Pentada": ("05-jul", "09-jul", "05–09/jul"),
    "39° Pentada": ("10-jul", "14-jul", "10–14/jul"),
    "40° Pentada": ("15-jul", "19-jul", "15–19/jul"),
    "41° Pentada": ("20-jul", "24-jul", "20–24/jul"),
    "42° Pentada": ("25-jul", "29-jul", "25–29/jul"),
    "43° Pentada": ("30-jul", "03-ago", "30/jul–03/ago"),
    "44° Pentada": ("04-ago", "08-ago", "04–08/ago"),
    "45° Pentada": ("09-ago", "13-ago", "09–13/ago"),
    "46° Pentada": ("14-ago", "18-ago", "14–18/ago"),
    "47° Pentada": ("19-ago", "23-ago", "19–23/ago"),
    "48° Pentada": ("24-ago", "28-ago", "24–28/ago"),
    "49° Pentada": ("29-ago", "02-set", "29/ago–02/set"),
    "50° Pentada": ("03-set", "07-set", "03–07/set"),
    "51° Pentada": ("08-set", "12-set", "08–12/set"),
    "52° Pentada": ("13-set", "17-set", "13–17/set"),
    "53° Pentada": ("18-set", "22-set", "18–22/set"),
    "54° Pentada": ("23-set", "27-set", "23–27/set"),
    "55° Pentada": ("28-set", "02-out", "28/set–02/out"),
    "56° Pentada": ("03-out", "07-out", "03–07/out"),
    "57° Pentada": ("08-out", "12-out", "08–12/out"),
    "58° Pentada": ("13-out", "17-out", "13–17/out"),
    "59° Pentada": ("18-out", "22-out", "18–22/out"),
    "60° Pentada": ("23-out", "27-out", "23–27/out"),
    "61° Pentada": ("28-out", "01-nov", "28/out–01/nov"),
    "62° Pentada": ("02-nov", "06-nov", "02–06/nov"),
    "63° Pentada": ("07-nov", "11-nov", "07–11/nov"),
    "64° Pentada": ("12-nov", "16-nov", "12–16/nov"),
    "65° Pentada": ("17-nov", "21-nov", "17–21/nov"),
    "66° Pentada": ("22-nov", "26-nov", "22–26/nov"),
    "67° Pentada": ("27-nov", "01-dez", "27/nov–01/dez"),
    "68° Pentada": ("02-dez", "06-dez", "02–06/dez"),
    "69° Pentada": ("07-dez", "11-dez", "07–11/dez"),
    "70° Pentada": ("12-dez", "16-dez", "12–16/dez"),
    "71° Pentada": ("17-dez", "21-dez", "17–21/dez"),
    "72° Pentada": ("22-dez", "26-dez", "22–26/dez"),
    "73° Pentada": ("27-dez", "31-dez", "27–31/dez"),
}


def generate_pentada_dict(year: int) -> dict[int, tuple[datetime, datetime]]:
    """
    Gera um dicionário {nº pentada: (data_inicial, data_final)} para o ano especificado.

    Parameters
    ----------
    year : int
        Ano para gerar a tabela de pentadas.

    Returns
    -------
    dict
        {nº pentada: (data_inicial, data_final)}
    """
    start = datetime(year, 1, 1)
    pentada_dict = {}
    for p in range(1, 74):
        start_day = start + timedelta(days=(p - 1) * 5)
        end_day = min(start_day + timedelta(days=4), datetime(year, 12, 31))
        pentada_dict[p] = (start_day, end_day)
    return pentada_dict


def date_to_pentada(date: datetime, year: int = None) -> int:
    """
    Converte uma data para o número da pentada correspondente.

    Parameters
    ----------
    date : datetime
        Data de interesse.
    year : int, optional
        Ano de referência. Se None, usa date.year.

    Returns
    -------
    int
        Número da pentada (1–73).
    """
    if year is None:
        year = date.year
    day_of_year = (date - datetime(year, 1, 1)).days + 1
    pentada = ((day_of_year - 1) // 5) + 1
    if pentada > 73:
        pentada = 73
    return pentada


def pentada_to_dates(pentada: int, year: int) -> tuple[datetime, datetime]:
    """
    Retorna a data inicial e final de uma pentada específica em um ano.

    Parameters
    ----------
    pentada : int
        Número da pentada (1–73).
    year : int

    Returns
    -------
    (datetime, datetime)
    """
    pentadas = generate_pentada_dict(year)
    return pentadas[pentada]


def pentada_label(pentada: int, year: int) -> str:
    """
    Retorna a legenda da pentada (ex: "06–10/jan").

    Parameters
    ----------
    pentada : int
        Número da pentada (1–73).
    year : int

    Returns
    -------
    str
    """
    start, end = pentada_to_dates(pentada, year)
    label = f"{start.day:02d}–{end.day:02d}/{start.strftime('%b')}"
    return label


def list_pentadas(year: int) -> list[str]:
    """
    Lista todas as legendas das 73 pentadas para o ano desejado.

    Parameters
    ----------
    year : int

    Returns
    -------
    List[str]
    """
    return [pentada_label(p, year) for p in range(1, 74)]


def show_pentadas_table(year: int):
    """
    Imprime no terminal uma tabela formatada com as 73 pentadas para um ano específico.

    A função exibe o número da pentada, a data de início, a data de fim
    e o rótulo correspondente, facilitando a visualização e verificação.
    """
    print(f"--- Tabela de Pentadas para o Ano de {year} ---")

    # Define o cabeçalho da tabela
    header = f"{'Pentada':<9} | {'Data Início':<12} | {'Data Fim':<12} | Rótulo"
    print(header)
    print("-" * (len(header) + 2))  # Adicionado +2 para alinhar melhor

    # Itera de 1 a 73 para obter os dados de cada pentada
    for p in range(1, 74):
        start_date, end_date = pentada_to_dates(p, year)

        # ====================================================================
        # CORREÇÃO DO RÓTULO APLICADA AQUI DENTRO
        # ====================================================================
        # Verifica se a pentada cruza para o mês seguinte
        if start_date.month != end_date.month:
            # Formato especial para mudança de mês: ex: "31/Jan–04/Fev"
            # Usamos locale para garantir os nomes dos meses em português
            # import locale
            # locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
            label_corrigido = (
                f"{start_date.strftime('%d/%b')}–{end_date.strftime('%d/%b')}"
            )
        else:
            # Formato padrão quando a pentada está no mesmo mês: ex: "01–05/Jan"
            label_corrigido = (
                f"{start_date.day:02d}–{end_date.day:02d}/{start_date.strftime('%b')}"
            )
        # ====================================================================

        # Formata as datas para o padrão dia/mês/ano
        start_str = start_date.strftime("%d/%m/%Y")
        end_str = end_date.strftime("%d/%m/%Y")

        # Imprime a linha formatada USANDO O RÓTULO CORRIGIDO
        print(f"{f'{p}ª':<9} | {start_str:<12} | {end_str:<12} | {label_corrigido}")
