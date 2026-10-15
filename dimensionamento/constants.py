"""Costanti fisiche e fattori di conversione.

Qui compaiono solo grandezze fisiche universali. I dati dell'ambiente di Marte
e i requisiti di missione sono in ``common.toml``; le scelte di progetto sono
nel file di input del gruppo.
"""

# Costante di Stefan-Boltzmann [W/(m^2 K^4)]
SIGMA_SB = 5.670374e-8

# Costante universale dei gas [J/(mol K)]
R_UNIVERSAL = 8.314462

# Masse molari [kg/mol]
M_O2 = 0.031998
M_N2 = 0.028014

# Intervalli di tempo [s]
HOUR = 3600.0
DAY = 86400.0          # giorno terrestre: base dei consumi per persona-giorno

# Energia [J]
KWH = 3.6e6

# Conversione fra areal density in g/cm^2 e kg/m^2
G_CM2 = 10.0
