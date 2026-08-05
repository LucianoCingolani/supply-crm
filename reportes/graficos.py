"""Geometría de los gráficos SVG.

La app no tiene ninguna dependencia JS ni build de Node, así que los gráficos
son SVG inline con las coordenadas calculadas acá. Los colores salen de la
paleta validada (ver PALETA abajo).
"""

from dataclasses import dataclass, field

# Paleta validada con los chequeos computables de la guía de visualización,
# contra la superficie real de las tarjetas (#ffffff):
#   banda de luminosidad OKLCH, piso de croma, y contraste >= 3:1.
# Cada barra es de un solo tono y va rotulada: no hay pares de color que el
# lector tenga que distinguir para saber qué es qué. Eso es deliberado —
# verde y rojo miden ΔE 4.1 bajo deuteranopía (indistinguibles), así que una
# apilada de tres colores no era viable con esta semántica.
PALETA = {
    'facturadas': {'relleno': '#0ca30c', 'pista': '#d1f0d1'},
    'activas':    {'relleno': '#d97706', 'pista': '#f5e3c8'},
    'perdidas':   {'relleno': '#d03b3b', 'pista': '#f5d5d5'},
    'consultas':  {'relleno': '#2a78d6', 'pista': '#cde2fb'},
}

TINTA_MUTED = '#898781'
GRILLA = '#e1e0d9'


@dataclass
class Punto:
    x: float
    y: float
    valor: int
    etiqueta_mes: str


@dataclass
class Serie:
    nombre: str
    color: str
    puntos: list = field(default_factory=list)
    # Si las series convergen en el borde derecho, los rótulos finales se
    # pisarían. Apilarlos los despega de su línea y se lee como ruido, así que
    # se suprime el de la serie menor: la leyenda y la tabla lo siguen diciendo.
    etiquetar_final: bool = True

    @property
    def polilinea(self):
        return ' '.join(f'{p.x:.1f},{p.y:.1f}' for p in self.puntos)

    @property
    def ultimo(self):
        return self.puntos[-1] if self.puntos else None


@dataclass
class GraficoLineas:
    ancho: int
    alto: int
    series: list
    grillas: list          # [(y, valor_tick)]
    etiquetas_x: list      # [(x, texto)]
    base_y: float
    izq: float
    der: float


def grafico_evolucion(filas, ancho=680, alto=200):
    """Dos series de conteos sobre un solo eje (misma unidad: cantidad de consultas).

    Nunca dos escalas: sería el error de gráfico más común y fabricaría una
    correlación inexistente.
    """
    pad_izq, pad_der, pad_arriba, pad_abajo = 38, 46, 14, 26
    plot_ancho = ancho - pad_izq - pad_der
    plot_alto = alto - pad_arriba - pad_abajo
    base_y = pad_arriba + plot_alto

    maximo = max([f['total'] for f in filas] + [1])
    tope = _tope_redondo(maximo)
    n = len(filas)

    # Se redondea acá: si no, el atributo sale como "98.80000000000001".
    def x_de(i):
        if n == 1:
            return round(pad_izq + plot_ancho / 2, 1)
        return round(pad_izq + i * plot_ancho / (n - 1), 1)

    def y_de(v):
        return round(pad_arriba + plot_alto - (v / tope) * plot_alto, 1)

    series = []
    for nombre, clave in (('Consultas', 'total'), ('Facturadas', 'facturadas')):
        color = PALETA['consultas' if clave == 'total' else 'facturadas']['relleno']
        puntos = [
            Punto(x=x_de(i), y=y_de(f[clave]), valor=f[clave], etiqueta_mes=f['etiqueta'])
            for i, f in enumerate(filas)
        ]
        series.append(Serie(nombre=nombre, color=color, puntos=puntos))

    _resolver_colision_de_rotulos(series)

    ticks = _ticks(tope)
    return GraficoLineas(
        ancho=ancho,
        alto=alto,
        series=series,
        grillas=[(y_de(t), t) for t in ticks],
        etiquetas_x=[(x_de(i), f['etiqueta']) for i, f in enumerate(filas)],
        base_y=base_y,
        izq=pad_izq,
        der=pad_izq + plot_ancho,
    )


#  Alto de línea del rótulo final, en unidades del viewBox (font-size 11).
SEPARACION_MINIMA_ROTULOS = 12


def _resolver_colision_de_rotulos(series):
    """Deja un solo rótulo final cuando dos series terminan demasiado juntas."""
    con_final = [s for s in series if s.ultimo]
    for i, a in enumerate(con_final):
        for b in con_final[i + 1:]:
            if abs(a.ultimo.y - b.ultimo.y) < SEPARACION_MINIMA_ROTULOS:
                menor = a if a.ultimo.valor <= b.ultimo.valor else b
                menor.etiquetar_final = False


def _tope_redondo(maximo):
    """Redondea el máximo hacia arriba a un número limpio para los ticks."""
    if maximo <= 5:
        return 5
    for paso in (10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if maximo <= paso:
            return paso
    return int(-(-maximo // 1000) * 1000)


def _ticks(tope):
    return [0, tope // 2, tope] if tope % 2 == 0 else [0, tope]
