"""
Busca o traçado real de uma rodovia no OpenStreetMap (via Overpass API) pelo
código dela (ex.: "SP-330"), pra desenhar no mapa sem exigir que o usuário
marque coordenadas manualmente.

Importante: isso é uma aproximação, não georreferenciamento oficial.
- O traçado vem de como a rodovia está mapeada no OSM, que pode estar
  incompleto (algumas rodovias têm poucas vias com a tag "ref" certa) ou
  ausente pra determinada rodovia.
- Rodovia com pista dupla vira duas linhas paralelas no OSM (uma por
  sentido) — a reconstrução abaixo escolhe uma única cadeia contínua
  (o "caminho mais longo" no grafo de vias conectadas), não as duas.
- A posição de um km específico ao longo do traçado é calculada por
  distância proporcional (mesmo princípio já usado pra posicionar frame
  dentro de um Segment), não por marco quilométrico oficial.

Se a busca falhar ou não achar nada, retorna None — cadastro de rodovia
nunca deve falhar por causa disso (é um enriquecimento, não requisito).
"""
import re
from typing import Optional

import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SECONDS = 25
# Overpass rejeita o User-Agent padrão do requests (bloqueio de bot
# genérico) com 406 — precisa de um User-Agent identificável.
OVERPASS_HEADERS = {"User-Agent": "GreenWayVision/0.1 (academic project, road geometry lookup)"}

Point = tuple[float, float]


def _extract_route_ref(road_name: str) -> Optional[str]:
    """Extrai o código da rodovia (ex.: "SP-330") do nome cadastrado
    (ex.: "SP-330 (Anhanguera)")."""
    match = re.match(r"^([A-Z]{2,3}-?\d{2,3})", road_name.strip().upper())
    return match.group(1) if match else None


def _query_overpass(ref: str) -> list[list[Point]]:
    query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
    area["ISO3166-1"="BR"][admin_level=2]->.br;
    (
      way["ref"="{ref}"]["highway"](area.br);
    );
    out geom;
    """
    response = requests.post(
        OVERPASS_URL,
        data={"data": query},
        headers=OVERPASS_HEADERS,
        timeout=OVERPASS_TIMEOUT_SECONDS + 5,
    )
    response.raise_for_status()
    data = response.json()

    ways = []
    for element in data.get("elements", []):
        geometry = element.get("geometry")
        if not geometry:
            continue
        ways.append([(point["lat"], point["lon"]) for point in geometry])
    return ways


def _distance(a: Point, b: Point) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _way_length(points: list[Point]) -> float:
    return sum(_distance(points[i - 1], points[i]) for i in range(1, len(points)))


class _Edge:
    __slots__ = ("other", "points", "length")

    def __init__(self, other: Point, points: list[Point], length: float):
        self.other = other  # nó na outra ponta
        self.points = points  # pontos indo do nó de origem até "other", em ordem
        self.length = length


def _build_graph(ways: list[list[Point]]) -> dict[Point, list[_Edge]]:
    graph: dict[Point, list[_Edge]] = {}

    def add_edge(a: Point, b: Point, points: list[Point]):
        graph.setdefault(a, []).append(_Edge(b, points, _way_length(points)))

    for way in ways:
        if len(way) < 2:
            continue
        start, end = way[0], way[-1]
        add_edge(start, end, way)
        add_edge(end, start, list(reversed(way)))

    return graph


def _connected_component(graph: dict[Point, list[_Edge]], start: Point) -> set[Point]:
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for edge in graph[node]:
            if edge.other not in seen:
                seen.add(edge.other)
                stack.append(edge.other)
    return seen


def _farthest_node(
    graph: dict[Point, list[_Edge]], start: Point, component: set[Point]
) -> tuple[Point, dict[Point, tuple[Point, list[Point]] | None]]:
    """DFS a partir de start, acumulando distância — retorna o nó mais
    distante alcançado e o "came_from" pra reconstruir o caminho até ele."""
    visited = {start}
    came_from: dict[Point, tuple[Point, list[Point]] | None] = {start: None}
    dist = {start: 0.0}
    stack = [start]
    farthest = start

    while stack:
        node = stack.pop()
        for edge in graph[node]:
            if edge.other in visited:
                continue
            visited.add(edge.other)
            dist[edge.other] = dist[node] + edge.length
            came_from[edge.other] = (node, edge.points)
            if dist[edge.other] > dist[farthest]:
                farthest = edge.other
            stack.append(edge.other)

    return farthest, came_from


def _longest_path_in_component(graph: dict[Point, list[_Edge]], component: set[Point]) -> list[Point]:
    start = next(iter(component))
    end_a, _ = _farthest_node(graph, start, component)
    end_b, came_from = _farthest_node(graph, end_a, component)

    # reconstrói o caminho de end_b até end_a seguindo came_from, depois inverte
    segments: list[list[Point]] = []
    node = end_b
    while came_from.get(node) is not None:
        prev, points = came_from[node]
        segments.append(points)
        node = prev
    segments.reverse()

    path: list[Point] = [end_a]
    for points in segments:
        # points vai de "prev" até o nó seguinte; pula o primeiro ponto
        # pra não duplicar o último ponto já adicionado
        path.extend(points[1:])
    return path


def _reconstruct_longest_path(ways: list[list[Point]]) -> list[Point]:
    """Entre todas as vias encontradas, monta um grafo por nós compartilhados
    e devolve o caminho contínuo mais longo — evita ziguezaguear entre as
    duas pistas de uma rodovia de pista dupla."""
    graph = _build_graph(ways)
    if not graph:
        return []

    visited_nodes: set[Point] = set()
    best_path: list[Point] = []
    best_length = -1.0

    for node in graph:
        if node in visited_nodes:
            continue
        component = _connected_component(graph, node)
        visited_nodes |= component

        path = _longest_path_in_component(graph, component)
        length = _way_length(path)
        if length > best_length:
            best_length = length
            best_path = path

    return best_path


def fetch_road_geometry(road_name: str) -> Optional[list[Point]]:
    ref = _extract_route_ref(road_name)
    if ref is None:
        return None

    try:
        ways = _query_overpass(ref)
        if not ways:
            return None
        path = _reconstruct_longest_path(ways)
        # menos de ~5km de traçado reconstruído não é útil o suficiente pra
        # representar uma rodovia — provavelmente achamos só um trevo isolado
        if _way_length(path) * 111 < 5:
            return None
        return path
    except Exception:
        # Overpass fora do ar, timeout, rodovia não encontrada, etc. —
        # cadastro segue sem geometria, usuário pode marcar manualmente.
        return None
